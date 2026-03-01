"""
Main routes blueprint for Ollama Dashboard.

This module is large and handles many endpoint variations; we relax a few
lint rules to keep the legacy surface area stable while improving readability.
"""
from datetime import datetime
import json
import os
import platform
import signal
import subprocess
import sys
import threading
import time

import psutil
import requests
from flask import Blueprint, Response, current_app, jsonify, render_template, request, stream_with_context

from app.routes import bp
from app.services.validators import InputValidator
from app.services.error_handling import (
    TransientErrorDetector,
    TIMEOUT_GENERATE,
    TIMEOUT_GENERATE_RETRY,
    TIMEOUT_PULL,
    TIMEOUT_DELETE,
    TIMEOUT_STOP,
    TIMEOUT_PS,
    TIMEOUT_DEFAULT,
)

import logging

# Set by init_app from app.config['OLLAMA_SERVICE']; tests patch this
ollama_service = None


def _get_ollama_service():
    """Get OllamaService from app context (injected by create_app)."""
    if ollama_service is not None:
        return ollama_service
    return current_app.config['OLLAMA_SERVICE']


def _get_timezone_name():
    """Get the local timezone name in a reliable way."""
    try:
        return datetime.now().astimezone().tzname()
    except Exception:
        try:
            # Fallback to time module
            return time.tzname[0] if time.tzname and len(time.tzname) > 0 else 'UTC'
        except Exception:
            # Last resort
            return 'UTC'


@bp.route('/')
def index():
    try:
        svc = _get_ollama_service()
        running_models = svc.get_running_models()
        available_models = svc.get_available_models()
        version = svc.get_ollama_version()
        system_stats = svc.get_system_stats()
        return render_template(
            'index.html',
            models=running_models,
            available_models=available_models,
            system_stats=system_stats,
            error=None,
            timezone=_get_timezone_name(),
            ollama_version=version,
            timestamp=int(time.time()),
        )
    except Exception as e:
        empty_stats = {
            'cpu_percent': 0,
            'memory': {'percent': 0, 'total': 0, 'available': 0, 'used': 0},
            'vram': {'percent': 0, 'total': 0, 'used': 0, 'free': 0},
            'disk': {'percent': 0, 'total': 0, 'used': 0, 'free': 0},
        }
        return render_template(
            'index.html',
            models=[],
            available_models=[],
            system_stats=empty_stats,
            error=str(e),
            timezone=_get_timezone_name(),
            ollama_version='Unknown',
            timestamp=int(time.time()),
        )

@bp.route('/api/test')
def test():
    return {"message": "API is working"}

def _get_ollama_url(endpoint=""):
    """Generate Ollama API URL."""
    host = current_app.config.get('OLLAMA_HOST', 'localhost')
    port = current_app.config.get('OLLAMA_PORT', 11434)
    return f"http://{host}:{port}/api/{endpoint}"


# Force kill the dashboard app and all children
@bp.route('/api/force_kill', methods=['POST'])
def force_kill_app():
    """Force kill the dashboard app and all its child processes."""
    current_pid = os.getpid()
    parent = psutil.Process(current_pid)
    killed_pids = []
    for child in parent.children(recursive=True):
        try:
            child.kill()
            killed_pids.append(child.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    try:
        parent.kill()
        killed_pids.append(current_pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        try:
            if platform.system() != "Windows":
                kill_signal = getattr(signal, 'SIGKILL', signal.SIGTERM)
            else:
                kill_signal = signal.SIGTERM
            os.kill(current_pid, kill_signal)
            killed_pids.append(current_pid)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    time.sleep(1)
    return jsonify({"success": True, "message": f"Force killed PIDs: {', '.join(map(str, killed_pids))}"})


def _validate_model_name(model_name):
    """Validate model name format. Returns (None, None) if valid, or (error_dict, status_code) if invalid."""
    is_valid, msg = InputValidator.validate_model_name(model_name)
    if not is_valid:
        return {"success": False, "error": msg, "message": msg}, 400
    return None, None


def _verify_model_unloaded(model_name, max_attempts=5, delay_seconds=1):
    """Poll /api/ps to confirm model is no longer loaded. Returns True when verified gone."""
    for _ in range(max_attempts):
        try:
            # Use the shared session from the service to honour connection pooling
            resp = _get_ollama_service()._session.get(_get_ollama_url("ps"), timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                if not any(m.get("name") == model_name for m in models):
                    return True
        except Exception:
            pass
        time.sleep(delay_seconds)
    return False


def _handle_model_error(response, model_name, operation="operation"):
    """Handle common model operation errors."""
    error_text = response.text.lower()

    if "exit status 2" in error_text or "llama runner process has terminated" in error_text:
        return {
            "success": False,
            "message": f"Model '{model_name}' is incompatible with your system. Try 'llama2:latest' or 'deepseek-r1:8b'."
        }, 400

    if "not found" in error_text:
        return {
            "success": False,
            "message": f"Model '{model_name}' not found. Please ensure it's installed."
        }, 404

    if "memory" in error_text.lower() or "ram" in error_text.lower():
        return {
            "success": False,
            "message": f"Model '{model_name}' is too large for available memory. Try a smaller model."
        }, 400

    return {
        "success": False,
        "message": f"Failed to {operation} model: {response.text}"
    }, response.status_code


@bp.route('/api/models/start/<model_name>', methods=['POST'], endpoint='api_start_model')
def start_model(model_name):
    """
    Start a model by loading it into memory.

    Attempts to generate with the model first, and if that fails,
    tries to pull the model from the registry before loading.
    Retries up to 3 times for transient connection errors (forcibly closed).
    """
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status
    try:
        # Check if model is already running
        running_models = _get_ollama_service().get_running_models()
        if any(model['name'] == model_name for model in running_models):
            return {"success": True, "message": f"Model {model_name} is already running"}

        # Check if Ollama service is running
        if not _get_ollama_service().get_service_status():
            return {"success": False, "message": "Ollama service is not running. Please start the service first."}, 503

        # Use service method to check if error is transient
        def _is_transient_error(error_text):
            """Check if error is transient (connection forcibly closed, etc.)"""
            return _get_ollama_service().is_transient_error(error_text)

        def _attempt_generate(retry_num=0, max_retries=3, timeout=60):
            """Attempt to generate with retry logic for transient errors.

            Args:
                retry_num: Current retry attempt (0-indexed)
                max_retries: Maximum number of retries (3)
                timeout: Request timeout in seconds (60s base, increases on retry)
            """
            try:
                # Explicit timeout prevents hanging on unresponsive Ollama
                response = requests.post(
                    _get_ollama_url("generate"),
                    json={"model": model_name, "prompt": "Hello", "stream": False, "keep_alive": "24h"},
                    timeout=timeout
                )

                if response.status_code == 200:
                    return {"success": True, "response": response}

                # Check if it's a transient error - check both text and JSON
                error_text = response.text
                try:
                    error_json = response.json()
                    if 'error' in error_json:
                        error_text = error_text + " " + str(error_json['error'])
                except Exception:
                    pass

                # Log the error for debugging
                current_app.logger.debug(f"Attempt {retry_num + 1}/{max_retries + 1}: Response status {response.status_code}")
                current_app.logger.debug(f"Error text: {error_text[:200]}")  # First 200 chars
                current_app.logger.debug(f"Is transient: {_is_transient_error(error_text)}")

                if _is_transient_error(error_text) and retry_num < max_retries:
                    wait_time = 2 ** retry_num  # Exponential backoff: 1s, 2s, 4s
                    current_app.logger.debug(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    return _attempt_generate(retry_num + 1, max_retries, timeout + 30)  # Increase timeout on retry

                return {"success": False, "response": response}

            except requests.exceptions.Timeout:
                if retry_num < max_retries:
                    time.sleep(2)
                    return _attempt_generate(retry_num + 1, max_retries, timeout + 30)
                raise
            except requests.exceptions.ConnectionError as e:
                if _is_transient_error(str(e)) and retry_num < max_retries:
                    time.sleep(2 ** retry_num)
                    return _attempt_generate(retry_num + 1, max_retries, timeout + 30)
                raise

        # Try to generate with the model to load it
        try:
            result = _attempt_generate()

            if result["success"]:
                # Clear the cache for running models to force a refresh
                # This ensures the UI shows the model as loaded immediately
                _get_ollama_service().clear_cache('running_models')
                # Force immediate refresh to populate cache with current state
                try:
                    _get_ollama_service().get_running_models(force_refresh=True)
                except Exception:
                    pass  # Best-effort refresh, don't fail if it errors
                return {"success": True, "message": f"Model {model_name} started successfully"}

            # Handle specific errors
            error_result, status_code = _handle_model_error(result["response"], model_name, "start")
            if error_result["success"] is False:
                # Try to pull the model first, then generate
                try:
                    # Pull timeout set to 10 minutes for large models
                    pull_response = requests.post(
                        _get_ollama_url("pull"),
                        json={"name": model_name, "stream": False},
                        timeout=600
                    )

                    if pull_response.status_code == 200:
                        # Try to generate again after pulling with retry logic
                        result = _attempt_generate()

                        if result["success"]:
                            # Clear the cache for running models to force a refresh
                            _get_ollama_service().clear_cache('running_models')
                            # Force immediate refresh to populate cache with current state
                            try:
                                _get_ollama_service().get_running_models(force_refresh=True)
                            except Exception:
                                pass  # Best-effort refresh, don't fail if it errors
                            return {"success": True, "message": f"Model {model_name} downloaded and started successfully"}

                        error_result, status_code = _handle_model_error(result["response"], model_name, "start after download")
                        return error_result, status_code
                    else:
                        return {"success": False, "message": f"Failed to download model: {pull_response.text}"}, 400

                except requests.exceptions.Timeout:
                    return {"success": False, "message": "Model download timed out. The model might be too large."}, 408

        except requests.exceptions.Timeout:
            return {"success": False, "message": "Model loading timed out after retries. Try a smaller model or check system resources."}, 408
        except requests.exceptions.ConnectionError as e:
            if _is_transient_error(str(e)):
                return {"success": False, "message": "Model loading failed after 3 retries due to connection issues. This can happen with large models on first load. Please try again."}, 503
            return {"success": False, "message": "Cannot connect to Ollama server. Please ensure Ollama is running."}, 503

    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500

@bp.route('/api/models/stop/<model_name>', methods=['POST'])
def stop_model(model_name):
    """Gracefully unload a model from memory using Ollama API.

    Uses keep_alive=0s to signal Ollama to unload the model.
    Does NOT kill processes (which would stop the entire Ollama service).
    """
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status
    try:
        # Verify Ollama service is running
        if not _get_ollama_service().get_service_status():
            return {"success": False, "message": "Ollama service is not running"}, 503

        # Check if model is currently running
        running_models = _get_ollama_service().get_running_models()
        if not any(m.get('name') == model_name for m in running_models):
            return {"success": False, "message": f"Model {model_name} is not currently running"}, 400

        # Gracefully unload the model using Ollama API
        # Per Ollama docs: empty prompt + keep_alive=0 (numeric) unloads immediately
        try:
            unload_response = requests.post(
                _get_ollama_url("generate"),
                json={
                    "model": model_name,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": 0
                },
                timeout=30
            )

            if unload_response.status_code == 200:
                _verify_model_unloaded(model_name)
                _get_ollama_service().clear_cache('running_models')
                try:
                    _get_ollama_service().get_running_models(force_refresh=True)
                except Exception:
                    pass
                return {"success": True, "message": f"Model {model_name} stopped successfully"}
            elif unload_response.status_code == 404:
                return {"success": False, "message": f"Model {model_name} not found"}, 404
            else:
                error_msg = f"Failed to stop model: HTTP {unload_response.status_code}"
                try:
                    error_detail = unload_response.json().get('error', '')
                    if error_detail:
                        error_msg += f" - {error_detail}"
                except Exception:
                    pass
                return {"success": False, "message": error_msg}, unload_response.status_code

        except requests.exceptions.Timeout:
            return {"success": False, "message": f"Timeout while stopping model {model_name}. The model may still be unloading."}, 504
        except requests.exceptions.RequestException as e:
            return {"success": False, "message": f"Network error while stopping model: {str(e)}"}, 503

    except Exception as e:
        current_app.logger.error(f"Unexpected error stopping model {model_name}: {str(e)}")
        return {"success": False, "message": f"Unexpected error stopping model: {str(e)}"}, 500


@bp.route('/api/models/restart/<model_name>', methods=['POST'])
def restart_model(model_name):
    """Restart a model by stopping then starting it.

    Atomically performs stop (if running) followed by warm start.
    If stop fails, does not proceed with start.
    """
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status
    try:
        # Verify Ollama service is running
        if not _get_ollama_service().get_service_status():
            return {"success": False, "message": "Ollama service is not running"}, 503

        # Check if model is currently running
        running_models = _get_ollama_service().get_running_models()
        is_running = any(m.get('name') == model_name for m in running_models)

        # Step 1: Stop the model if it's running
        if is_running:
            try:
                unload_response = requests.post(
                    _get_ollama_url("generate"),
                    json={
                        "model": model_name,
                        "prompt": "",
                        "stream": False,
                        "keep_alive": 0
                    },
                    timeout=30
                )

                if unload_response.status_code not in [200, 404]:
                    error_msg = f"Failed to stop model during restart: HTTP {unload_response.status_code}"
                    try:
                        error_detail = unload_response.json().get('error', '')
                        if error_detail:
                            error_msg += f" - {error_detail}"
                    except Exception:
                        pass
                    return {"success": False, "message": error_msg}, unload_response.status_code

            except requests.exceptions.Timeout:
                return {"success": False, "message": f"Timeout while stopping model {model_name} during restart"}, 504
            except requests.exceptions.RequestException as e:
                return {"success": False, "message": f"Network error while stopping model: {str(e)}"}, 503

            time.sleep(3)
            _verify_model_unloaded(model_name)
            _get_ollama_service().clear_cache('running_models')

        # Step 2: Start the model (warm start with retry logic)
        max_retries = 3
        retry_delay = 1
        last_error = None

        for attempt in range(max_retries):
            try:
                # Warm start with extended keep_alive
                start_response = requests.post(
                    _get_ollama_url("generate"),
                    json={
                        "model": model_name,
                        "prompt": "test",
                        "stream": False,
                        "keep_alive": "24h"
                    },
                    timeout=120
                )

                if start_response.status_code == 200:
                    message = f"Model {model_name} restarted successfully"
                    if attempt > 0:
                        message += f" (after {attempt + 1} attempts)"
                    return {"success": True, "message": message}
                elif start_response.status_code == 404:
                    # Model not found - if first attempt, try pulling it
                    if attempt == 0:
                        current_app.logger.info(f"Model {model_name} not found, attempting to pull")
                        try:
                            pull_response = requests.post(
                                _get_ollama_url("pull"),
                                json={"name": model_name},
                                timeout=600
                            )
                            if pull_response.status_code == 200:
                                continue  # Retry start after successful pull
                        except Exception as pull_error:
                            current_app.logger.error(f"Failed to pull model: {str(pull_error)}")
                    return {"success": False, "message": f"Model {model_name} not found"}, 404
                else:
                    last_error = f"HTTP {start_response.status_code}"
                    try:
                        error_detail = start_response.json().get('error', '')
                        if error_detail:
                            last_error += f" - {error_detail}"
                    except Exception:
                        pass

                    # Check if this is a transient error worth retrying
                    if start_response.status_code in [500, 502, 503, 504] and attempt < max_retries - 1:
                        time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                        continue
                    else:
                        return {"success": False, "message": f"Failed to restart model: {last_error}"}, start_response.status_code

            except requests.exceptions.Timeout:
                last_error = "Timeout"
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
                else:
                    return {"success": False, "message": f"Timeout while restarting model {model_name}"}, 504
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
                else:
                    return {"success": False, "message": f"Network error while restarting model: {str(e)}"}, 503

        return {"success": False, "message": f"Failed to restart model after {max_retries} attempts: {last_error}"}, 500

    except Exception as e:
        current_app.logger.error(f"Unexpected error restarting model {model_name}: {str(e)}")
        return {"success": False, "message": f"Unexpected error restarting model: {str(e)}"}, 500


@bp.route('/api/models/info/<model_name>')
def get_model_info(model_name):
    """Get detailed information about a specific model."""
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status
    try:
        response = _get_ollama_service()._session.post(
            _get_ollama_url("show"),
            json={"name": model_name},
            timeout=10
        )
        return response.json() if response.status_code == 200 else ({"error": "Model not found"}, 404)
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/system/stats')
def get_system_stats():
    """Get current system statistics."""
    try:
        stats = _get_ollama_service().get_system_stats()
        return stats if stats else ({"error": "System monitoring not available"}, 503)
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/available')
def get_available_models():
    """Get list of all available models."""
    try:
        models = _get_ollama_service().get_available_models()
        # Add has_custom_settings flag for each model (to be used in UI)
        for m in models:
            m['has_custom_settings'] = _get_ollama_service().has_custom_model_settings(m.get('name'))
        return {"models": models}
    except Exception as e:
        return {"error": str(e), "models": []}, 500


@bp.route('/api/models/running')
def get_running_models():
    """Get list of currently running models. Always fetches fresh from Ollama for accuracy."""
    try:
        models = _get_ollama_service().get_running_models(force_refresh=True)
        return {"models": models}
    except Exception as e:
        return {"error": str(e), "models": []}, 500


@bp.route('/api/models/settings/<model_name>')
def api_get_model_settings(model_name):
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status
    try:
        data = _get_ollama_service().get_model_settings_with_fallback(model_name)
        if data is None:
            return {"error": f"Settings not available for model {model_name}"}, 404
        return data
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/settings/recommended/<model_name>')
def api_get_recommended_settings(model_name):
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status
    try:
        data = _get_ollama_service().get_model_settings_with_fallback(model_name)
        if data is None:
            return {"error": f"Settings not available for model {model_name}"}, 404
        # Return only recommended (no save)
        return {"model": model_name, "settings": data.get('settings'), "source": data.get('source', 'recommended')}
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/settings/<model_name>', methods=['POST'])
def api_save_model_settings(model_name):
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status
    try:
        payload = request.get_json() or {}
        success = _get_ollama_service().save_model_settings(model_name, payload, source='user')
        if success:
            return _json_success(f"Settings for {model_name} saved.")
        return _json_error(f"Failed to save settings for {model_name}", status=500)
    except Exception as e:
        return _json_error(f"Unexpected error saving model settings: {str(e)}")


@bp.route('/api/models/settings/<model_name>', methods=['DELETE'])
def api_delete_model_settings(model_name):
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status
    try:
        success = _get_ollama_service().delete_model_settings(model_name)
        if success:
            return _json_success(f"Settings for {model_name} deleted.")
        return _json_error(f"Settings for {model_name} not found.", status=404)
    except Exception as e:
        return _json_error(f"Unexpected error deleting model settings: {str(e)}")


@bp.route('/api/models/settings/migrate', methods=['POST'])
def api_migrate_model_settings():
    try:
        return _json_error("Global settings migration no longer supported", status=410)
    except Exception as e:
        return _json_error(f"Migration error: {str(e)}")


@bp.route('/api/models/settings/apply_all_recommended', methods=['POST'])
def api_apply_all_recommended():
    try:
        models = _get_ollama_service().get_available_models()
        applied = 0
        errors = []
        for m in models:
            try:
                name = m.get('name')
                settings_data = _get_ollama_service().get_model_settings_with_fallback(name)
                if settings_data and settings_data.get('settings'):
                    success = _get_ollama_service().save_model_settings(name, settings_data['settings'], source='recommended')
                    if success:
                        applied += 1
            except Exception as e:
                errors.append(str(e))
        return _json_success(f"Applied recommended settings to {applied} models.", extra={'applied': applied, 'errors': errors})
    except Exception as e:
        return _json_error(f"Error applying all recommended settings: {str(e)}")


@bp.route('/api/models/settings/<model_name>/reset', methods=['POST'])
def api_reset_model_settings(model_name):
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status
    try:
        # Get recommended settings via fallback
        settings_data = _get_ollama_service().get_model_settings_with_fallback(model_name)
        if not settings_data or not settings_data.get('settings'):
            return _json_error(f"Could not determine recommended settings for {model_name}", status=500)
        # Save as recommended (not user)
        success = _get_ollama_service().save_model_settings(model_name, settings_data['settings'], source='recommended')
        if success:
            return _json_success(f"Settings for {model_name} reset to recommended defaults.")
        return _json_error(f"Failed to reset settings for {model_name}", status=500)
    except Exception as e:
        return _json_error(f"Unexpected error resetting model settings: {str(e)}")


@bp.route('/api/version')
def get_ollama_version():
    """Get Ollama version."""
    try:
        version = _get_ollama_service().get_ollama_version()
        return {"version": version}
    except Exception as e:
        return {"error": str(e), "version": "Unknown"}, 500


@bp.route('/api/models/bulk/start', methods=['POST'])
def bulk_start_models():
    """Start multiple models in bulk."""
    try:
        data = request.get_json(silent=True) or {}
        model_names = data.get('models', [])
        if not isinstance(model_names, list):
            model_names = []
        results = []
        svc = _get_ollama_service()

        for model_name in model_names:
            # Validate each model name individually
            is_valid, msg = InputValidator.validate_model_name(model_name)
            if not is_valid:
                results.append({"model": model_name, "success": False, "error": msg})
                continue
            try:
                response = svc._session.post(
                    _get_ollama_url("generate"),
                    json={"model": model_name, "prompt": "Hello", "stream": False, "keep_alive": "24h"},
                    timeout=60
                )
                results.append({
                    "model": model_name,
                    "success": response.status_code == 200,
                    "error": response.text if response.status_code != 200 else None
                })
            except Exception as e:
                results.append({"model": model_name, "success": False, "error": str(e)})

        # Invalidate the running-models cache so next GET /api/models/running reflects reality
        svc.clear_cache('running_models')
        return {"results": results}
    except Exception as e:
        return {"error": str(e)}, 500

@bp.route('/api/chat', methods=['POST'])
def chat():
    """
    Handle chat requests with Ollama models.

    Supports both streaming and non-streaming responses.
    """
    try:
        data = request.get_json()
        model_name = data.get('model')
        prompt = data.get('prompt')
        stream = data.get('stream', False)
        context = data.get('context', [])

        if not model_name or not prompt:
            return {"error": "Model name and prompt are required"}, 400

        # Verify model exists
        if not _get_ollama_service().get_model_info_cached(model_name):
            return {"error": f"Model '{model_name}' not found. Please ensure it's installed."}, 404

        chat_data = {
            "model": model_name,
            "prompt": prompt,
            "stream": stream
        }
        if context:
            chat_data["context"] = context

        # Use service defaults then merge per-model recommended/ saved settings (global settings removed)
        options = _get_ollama_service().get_default_settings()
        # Merge per-model settings (fallback recommended if no saved entry)
        try:
            model_settings_entry = _get_ollama_service().get_model_settings_with_fallback(model_name)
            if model_settings_entry and isinstance(model_settings_entry.get('settings'), dict):
                for k, v in model_settings_entry['settings'].items():
                    options[k] = v
        except Exception as e:
            print(f"Failed to merge per-model settings for {model_name}: {e}")
        chat_data["options"] = options

        try:
            response = _get_ollama_service()._session.post(
                _get_ollama_url("generate"),
                json=chat_data,
                timeout=120,
                stream=stream
            )
        except requests.exceptions.Timeout:
            return {"error": "Request timed out. Try a smaller model."}, 408
        except requests.exceptions.ConnectionError:
            return {"error": "Cannot connect to Ollama server. Please ensure Ollama is running."}, 503

        if response.status_code == 200:
            return (response.content, 200, {'Content-Type': 'text/plain'}) if stream else response.json()

        # Handle error responses
        error_result, status_code = _handle_model_error(response, model_name, "chat with")
        return error_result, status_code

    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}, 500


@bp.route('/api/models/delete/<model_name>', methods=['DELETE'])
def delete_model(model_name):
    """Delete a model and its settings."""
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status
    try:
        # Attempt to delete model from Ollama backend
        host, port = _get_ollama_service().get_ollama_host_port()
        url = f"http://{host}:{port}/api/delete"
        response = _get_ollama_service()._session.delete(url, json={"name": model_name}, timeout=30)
        if response.status_code != 200:
            try:
                err_json = response.json()
                error_msg = err_json.get("error") or err_json.get("message") or response.text
            except Exception:
                error_msg = response.text
            return jsonify({"success": False, "message": f"Failed to delete model: {error_msg}"}), 400

        # Remove model settings
        from app.services.model_settings_helpers import delete_model_settings_entry
        settings_deleted = delete_model_settings_entry(_get_ollama_service(), model_name)

        return jsonify({
            "success": True,
            "message": f"Model '{model_name}' deleted successfully. Settings removed: {settings_deleted}"
        }), 200
    except Exception as exc:
        return jsonify({"success": False, "message": f"Exception: {str(exc)}"}), 500



@bp.route('/metrics', methods=['GET'])
def prometheus_metrics():
    """Prometheus metrics are not implemented."""
    return jsonify({"error": "Prometheus metrics are not enabled"}), 501

@bp.route('/ping', methods=['GET'])
def ping():
    """Lightweight health check for orchestrators (Docker, K8s, load balancers)."""
    return jsonify({'status': 'ok'}), 200


@bp.route('/health', methods=['GET'])
def simple_health():
    """Simple health endpoint for monitoring."""

    try:
        health = _get_ollama_service().get_component_health()
        if health.get('background_thread_alive'):
            return jsonify({'status': 'ok'}), 200
        else:
            return jsonify({'status': 'degraded'}), 503
    except Exception:
        return jsonify({'status': 'error'}), 500


@bp.route('/api/chat/history', methods=['GET'])
def get_chat_history():
    """Get chat history."""
    try:
        history = _get_ollama_service().get_chat_history()
        return {"history": history}
    except Exception as e:
        return {"error": str(e)}, 500


# Max JSON payload size for chat history (1MB) to prevent DoS
MAX_CHAT_PAYLOAD_BYTES = 1024 * 1024


@bp.route('/api/chat/history', methods=['POST'])
def save_chat_history():
    """Save a chat session."""
    try:
        if request.content_length and request.content_length > MAX_CHAT_PAYLOAD_BYTES:
            return {"error": f"Payload too large (max {MAX_CHAT_PAYLOAD_BYTES} bytes)"}, 413
        data = request.get_json()
        if data is None and request.get_data():
            return {"error": "Invalid JSON"}, 400
        _get_ollama_service().save_chat_session(data or {})
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/performance/<model_name>')
def get_model_performance(model_name):
    """Get performance metrics for a model."""
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status
    try:
        performance = _get_ollama_service().get_model_performance(model_name)
        return performance
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/system/stats/history')
def get_system_stats_history():
    """Get historical system statistics."""
    try:
        history = _get_ollama_service().get_system_stats_history()
        return {"history": history}
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/service/status')
def get_service_status():
    """Get Ollama service status."""
    try:
        status = _get_ollama_service().get_service_status() or False
        return {"status": "running" if status else "stopped", "running": status}
    except Exception as e:
        return {"error": str(e), "status": "unknown", "running": False}, 500

@bp.route('/api/health')
def api_health():
    """Component health: background thread, cache ages, failure counters."""
    try:
        return _get_ollama_service().get_component_health()
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/service/start', methods=['POST'])
def start_service():
    """Start the Ollama service."""
    try:
        result = _get_ollama_service().start_service() or {}
        if not result:
            return {"success": False, "message": "Service start returned no result"}, 500
        return (result, 200) if isinstance(result, dict) and result.get("success") else (result, 500)
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500


@bp.route('/api/service/stop', methods=['POST'])
def stop_service():
    """Stop the Ollama service."""
    try:
        result = _get_ollama_service().stop_service()
        return (result, 200) if isinstance(result, dict) and result.get("success") else (result, 500)
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500


@bp.route('/api/service/restart', methods=['POST'])
def restart_service():
    """Restart the Ollama service."""
    try:
        result = _get_ollama_service().restart_service()
        return (result, 200) if isinstance(result, dict) and result.get("success") else (result, 500)
    except Exception as e:
        return {"success": False, "message": f"Unexpected error restarting service: {str(e)}"}, 500

@bp.route('/api/full/restart', methods=['POST'])
def full_restart():
    """Perform comprehensive application restart (caches + settings + background thread). Does NOT restart Ollama service."""
    try:
        result = _get_ollama_service().full_restart()
        return (result, 200) if result.get("success") else (result, 500)
    except Exception as e:
        return {"success": False, "message": f"Unexpected error performing full restart: {str(e)}"}, 500


@bp.route('/api/models/memory/usage')
def get_models_memory_usage():
    """Get memory usage information for running models."""
    try:
        memory_usage = _get_ollama_service().get_models_memory_usage()
        return memory_usage if memory_usage else ({"error": "Memory monitoring not available"}, 503)
    except Exception as e:
        return {"error": str(e)}, 500

@bp.route('/api/models/downloadable')
def api_get_downloadable_models():
    """Get list of downloadable models."""
    try:
        category = request.args.get('category', 'best')
        models = _get_ollama_service().get_downloadable_models(category)
        return {"models": models}
    except Exception as e:
        current_app.logger.error(f"Error in downloadable models endpoint: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 500

def _json_success(message, extra=None, status=200):
    payload = {"success": True, "message": message}
    if extra:
        payload.update(extra)
    return jsonify(payload), status

def _json_error(message, status=500):
    """Return a standardized JSON error response."""
    return jsonify({"success": False, "error": message, "message": message}), status

@bp.route('/api/models/pull/<model_name>', methods=['POST'])
def api_pull_model(model_name):
    """Pull a model with optional streaming progress updates."""
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status
    stream = request.args.get('stream', 'false').lower() == 'true'
    try:
        if stream:
            def generate():
                for update in _get_ollama_service().pull_model_stream(model_name):
                    yield f"data: {json.dumps(update)}\n\n"

            return Response(stream_with_context(generate()), mimetype='text/event-stream')

        result = _get_ollama_service().pull_model(model_name)
        if isinstance(result, dict) and result.get("success"):
            return _json_success(result.get("message", f"Pulled {model_name}"))
        return _json_error(result.get("message", "Failed to pull model"))
    except Exception as e:
        return _json_error(f"Unexpected error pulling model: {str(e)}")


# Removed duplicate warm-load start_model route; unified logic provided earlier with endpoint 'api_start_model'.


@bp.route('/api/test-models-debug')
def test_models_debug():
    """Test endpoint to debug model counts."""
    best = _get_ollama_service().get_best_models()
    all_models = _get_ollama_service().get_all_downloadable_models()
    best_via_method = _get_ollama_service().get_downloadable_models('best')
    all_via_method = _get_ollama_service().get_downloadable_models('all')

    return {
        "best_count": len(best),
        "all_downloadable_count": len(all_models),
        "via_method_best_count": len(best_via_method),
        "via_method_all_count": len(all_via_method),
        "via_method_all_names": [m['name'] for m in all_via_method]
    }


# Legacy global settings page removed.


@bp.route('/admin/model-defaults')
def admin_model_defaults():
    return render_template('admin_model_defaults.html')


# Global /api/settings endpoint removed (legacy global settings deprecated).


def init_app(app):
    """Initialize the blueprint with the app."""
    global ollama_service
    svc = app.config['OLLAMA_SERVICE']
    ollama_service = svc  # For test compatibility (tests patch app.routes.main.ollama_service)
    # init_app() is the canonical place to call OllamaService.init_app(); do not duplicate it here.
    # Monitoring endpoints are stored on the blueprint object so they are only registered once
    # even when create_app() is called multiple times (e.g. in tests).
    if not getattr(bp, '_monitoring_registered', False):
        from app.routes.monitoring import create_monitoring_endpoints
        create_monitoring_endpoints(bp, svc)
        bp._monitoring_registered = True
    # Template filters (`datetime` and `time_ago`) are registered in app factory via app.__init__.
    # Avoid duplicate registration here to prevent platform-specific filter overrides.
    app.register_blueprint(bp)
