"""
Main routes for Ollama Dashboard.
"""
import os
import time
import signal
import sys
import subprocess
import threading
import platform
import requests
import psutil
from flask import render_template, current_app, request, jsonify
from app.services.ollama import OllamaService
from app.routes import bp
from datetime import datetime
import pytz

# Initialize service without app
ollama_service = OllamaService()

def _get_timezone_name():
    """Get the local timezone name in a reliable way."""
    try:
        # Try to get timezone from pytz
        local_tz = datetime.now(pytz.timezone('UTC')).astimezone()
        return local_tz.tzname()
    except:
        try:
            # Fallback to time module
            import time
            return time.tzname[0] if time.tzname and len(time.tzname) > 0 else 'UTC'
        except:
            # Last resort
            return 'UTC'


@bp.route('/')
def index():
    try:
        # Get the current app context
        if not ollama_service.app:
            ollama_service.init_app(current_app)
        running_models = ollama_service.get_running_models()
        available_models = ollama_service.get_available_models()
        version = ollama_service.get_ollama_version()
        system_stats = ollama_service.get_system_stats()
        return render_template('index.html',
                             models=running_models,
                             available_models=available_models,
                             system_stats=system_stats,
                             error=None,
                             timezone=_get_timezone_name(),
                             ollama_version=version,
                             timestamp=int(time.time()))
    except Exception as e:
        return render_template('index.html',
                             models=[],
                             available_models=[],
                             system_stats={'cpu_percent': 0, 'memory': {'percent': 0, 'total': 0, 'available': 0, 'used': 0}, 'vram': {'percent': 0, 'total': 0, 'used': 0, 'free': 0}, 'disk': {'percent': 0, 'total': 0, 'used': 0, 'free': 0}},
                             error=str(e),
                             timezone=_get_timezone_name(),
                             ollama_version='Unknown',
                             timestamp=int(time.time()))

@bp.route('/api/test')
def test():
    return {"message": "API is working"}

def _get_ollama_url(endpoint=""):
    """Generate Ollama API URL."""
    host = ollama_service.app.config.get('OLLAMA_HOST')
    port = ollama_service.app.config.get('OLLAMA_PORT')
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


# Reload API: kills current process and starts a new one
@bp.route('/api/reload_app', methods=['POST'])
def reload_app():
    """Reload the application by stopping current instance and starting a new one."""
    try:
        if not sys.executable or not os.path.exists(sys.executable):
            return jsonify({
                'status': 'error',
                'message': 'Cannot determine Python executable path. Reload not available.'
            }), 500

        if ollama_service.app:
            try:
                ollama_service.clear_all_caches()
            except Exception as e:
                current_app.logger.warning(f"Error clearing caches before reload: {e}")

        def restart():
            """Restart the application in a daemon thread."""
            try:
                time.sleep(1)
                script_path = None
                try:
                    if len(sys.argv) > 0:
                        script_arg = sys.argv[0]
                        if os.path.exists(script_arg):
                            script_path = os.path.abspath(script_arg)
                        elif os.path.exists(os.path.join(os.getcwd(), script_arg)):
                            script_path = os.path.abspath(os.path.join(os.getcwd(), script_arg))
                except Exception as e:
                    current_app.logger.warning(f"Error detecting script from sys.argv: {e}")

                if not script_path or not os.path.exists(script_path):
                    try:
                        current_file = os.path.abspath(__file__)
                        current_dir = os.path.dirname(current_file)
                        parent_dir = os.path.dirname(current_dir)
                        potential_path = os.path.join(parent_dir, 'ollama_dashboard.py')
                        if os.path.exists(potential_path):
                            script_path = potential_path
                        else:
                            potential_path = os.path.join(parent_dir, 'wsgi.py')
                            if os.path.exists(potential_path):
                                script_path = potential_path
                    except Exception as e:
                        current_app.logger.warning(f"Error detecting script from file paths: {e}")

                if not script_path or not os.path.exists(script_path):
                    script_path = 'ollama_dashboard.py'
                    current_app.logger.warning(f"Could not detect script path, using default: {script_path}")

                python = sys.executable
                if not python or not os.path.exists(python):
                    current_app.logger.error("Python executable not found, cannot restart")
                    return

                try:
                    if os.path.exists(script_path):
                        current_dir = os.path.dirname(os.path.abspath(script_path))
                    else:
                        current_dir = os.getcwd()
                except Exception:
                    current_dir = os.getcwd()

                current_pid = os.getpid()
                try:
                    parent = psutil.Process(current_pid)
                except Exception as e:
                    current_app.logger.error(f"Cannot get process info: {e}")
                    return

                try:
                    for child in parent.children(recursive=True):
                        try:
                            child.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        except Exception:
                            pass
                except Exception as e:
                    current_app.logger.warning(f"Error killing child processes: {e}")

                time.sleep(0.5)
                restart_cmd = [python, script_path]
                try:
                    if platform.system() == "Windows":
                        try:
                            subprocess.Popen(
                                restart_cmd,
                                cwd=current_dir,
                                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                                close_fds=True,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                        except (AttributeError, ValueError, TypeError):
                            subprocess.Popen(
                                restart_cmd,
                                cwd=current_dir,
                                creationflags=subprocess.DETACHED_PROCESS,
                                close_fds=True,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                    else:
                        subprocess.Popen(
                            restart_cmd,
                            cwd=current_dir,
                            start_new_session=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                except Exception as e:
                    current_app.logger.error(f"Failed to start new process: {e}")
                    try:
                        subprocess.Popen(restart_cmd, cwd=current_dir)
                    except Exception as e2:
                        current_app.logger.error(f"Fallback restart also failed: {e2}")
                        return

                time.sleep(0.5)
                try:
                    parent.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                except Exception:
                    try:
                        if platform.system() != "Windows":
                            kill_signal = getattr(signal, 'SIGKILL', signal.SIGTERM)
                        else:
                            kill_signal = signal.SIGTERM
                        os.kill(current_pid, kill_signal)
                    except (ProcessLookupError, PermissionError, OSError):
                        pass
            except Exception as e:
                try:
                    current_app.logger.exception(f"Critical error during restart: {e}")
                except Exception:
                    pass

        threading.Thread(target=restart, daemon=True).start()
        return jsonify({
            'status': 'restarting',
            'message': 'Application is restarting. Please wait a few seconds and refresh the page.'
        }), 202

    except Exception as e:
        current_app.logger.exception(f"Error during app reload: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to reload application: {str(e)}'
        }), 500


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
    import time

    try:
        # Check if model is already running
        running_models = ollama_service.get_running_models()
        if any(model['name'] == model_name for model in running_models):
            return {"success": True, "message": f"Model {model_name} is already running"}

        # Check if Ollama service is running
        if not ollama_service.get_service_status():
            return {"success": False, "message": "Ollama service is not running. Please start the service first."}, 503

        def _is_transient_error(error_text):
            """Check if error is transient (connection forcibly closed, etc.)"""
            transient_indicators = [
                'forcibly closed',
                'connection reset',
                'broken pipe',
                'wsarecv',
                'connection aborted'
            ]
            error_lower = error_text.lower()
            return any(indicator in error_lower for indicator in transient_indicators)

        def _attempt_generate(retry_num=0, max_retries=3, timeout=60):
            """Attempt to generate with retry logic for transient errors"""
            try:
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
                except:
                    pass

                # Log the error for debugging
                print(f"[DEBUG] Attempt {retry_num + 1}/{max_retries + 1}: Response status {response.status_code}")
                print(f"[DEBUG] Error text: {error_text[:200]}")  # First 200 chars
                print(f"[DEBUG] Is transient: {_is_transient_error(error_text)}")

                if _is_transient_error(error_text) and retry_num < max_retries:
                    wait_time = 2 ** retry_num  # Exponential backoff: 1s, 2s, 4s
                    print(f"[DEBUG] Retrying in {wait_time}s...")
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
                return {"success": True, "message": f"Model {model_name} started successfully"}

            # Handle specific errors
            error_result, status_code = _handle_model_error(result["response"], model_name, "start")
            if error_result["success"] is False:
                # Try to pull the model first, then generate
                try:
                    pull_response = requests.post(
                        _get_ollama_url("pull"),
                        json={"name": model_name, "stream": False},
                        timeout=600
                    )

                    if pull_response.status_code == 200:
                        # Try to generate again after pulling with retry logic
                        result = _attempt_generate()

                        if result["success"]:
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
                return {"success": False, "message": f"Model loading failed after 3 retries due to connection issues. This can happen with large models on first load. Please try again."}, 503
            return {"success": False, "message": "Cannot connect to Ollama server. Please ensure Ollama is running."}, 503

    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500

    return error_result, status_code

@bp.route('/api/models/stop/<model_name>', methods=['POST'])
def stop_model(model_name):
    try:
        import subprocess
        import signal
        import time
        import psutil

        # Ensure service is initialized before using its config
        if not ollama_service.app:
            ollama_service.init_app(current_app)

        # First try to unload the model gracefully using Ollama API
        try:
            unload_response = requests.post(
                _get_ollama_url("generate"),
                json={"model": model_name, "prompt": "", "stream": False, "keep_alive": "0s"},
                timeout=5
            )
            if unload_response.status_code == 200:
                return {"success": True, "message": f"Model {model_name} unloaded successfully"}
        except Exception as e:
            print(f"Graceful unload failed for {model_name}: {str(e)}")

        # If graceful unload fails, try to find and kill Ollama processes
        killed_processes = []
        force_killed = False

        try:
            # Narrow process selection: exact name match or standalone 'ollama' token in cmdline
            ollama_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    name = (proc.info.get('name') or '').lower()
                    cmdline = proc.info.get('cmdline') or []
                    cmd_tokens = [str(c).lower() for c in cmdline]
                    if name == 'ollama' or any(t == 'ollama' or t.endswith(os.sep + 'ollama') or t.endswith('/ollama') for t in cmd_tokens):
                        ollama_processes.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if ollama_processes:
                # Try graceful termination first
                for proc in ollama_processes:
                    try:
                        proc.terminate()
                        killed_processes.append(proc.pid)
                    except Exception as e:
                        print(f"Failed to terminate process {proc.pid}: {str(e)}")

                # Wait a bit for graceful termination
                time.sleep(2)

                # Force kill any remaining processes
                for proc in ollama_processes:
                    try:
                        if proc.is_running():
                            proc.kill()
                            force_killed = True
                            print(f"Force killed process {proc.pid}")
                    except Exception as e:
                        print(f"Failed to kill process {proc.pid}: {str(e)}")

                if killed_processes:
                    message = f"Stopped Ollama processes (PIDs: {', '.join(map(str, killed_processes))})"
                    if force_killed:
                        message += " - Force kill was required"
                    return {"success": True, "message": message, "force_killed": force_killed}
                else:
                    return {"success": False, "message": "No Ollama processes found to stop"}
            else:
                return {"success": False, "message": "No running Ollama processes found"}

        except Exception as e:
            return {"success": False, "message": f"Failed to stop Ollama processes: {str(e)}"}

    except Exception as e:
        return {"success": False, "message": f"Unexpected error stopping model: {str(e)}"}, 500

@bp.route('/api/models/info/<model_name>')
def get_model_info(model_name):
    """Get detailed information about a specific model."""
    try:
        response = requests.post(
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
        if not ollama_service.app:
            ollama_service.init_app(current_app)

        stats = ollama_service.get_system_stats()
        return stats if stats else ({"error": "System monitoring not available"}, 503)
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/available')
def get_available_models():
    """Get list of all available models."""
    try:
        models = ollama_service.get_available_models()
        # Add has_custom_settings flag for each model (to be used in UI)
        for m in models:
            m['has_custom_settings'] = ollama_service._has_custom_settings(m.get('name'))
        return {"models": models}
    except Exception as e:
        return {"error": str(e), "models": []}, 500


@bp.route('/api/models/running')
def get_running_models():
    """Get list of currently running models."""
    try:
        models = ollama_service.get_running_models()
        return models
    except Exception as e:
        return {"error": str(e), "models": []}, 500


@bp.route('/api/models/settings/<model_name>')
def api_get_model_settings(model_name):
    try:
        if not ollama_service.app:
            ollama_service.init_app(current_app)
        data = ollama_service.get_model_settings_with_fallback(model_name)
        if data is None:
            return {"error": f"Settings not available for model {model_name}"}, 404
        return data
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/settings/recommended/<model_name>')
def api_get_recommended_settings(model_name):
    try:
        if not ollama_service.app:
            ollama_service.init_app(current_app)
        data = ollama_service.get_model_settings_with_fallback(model_name)
        if data is None:
            return {"error": f"Settings not available for model {model_name}"}, 404
        # Return only recommended (no save)
        return {"model": model_name, "settings": data.get('settings'), "source": data.get('source', 'recommended')}
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/settings/<model_name>', methods=['POST'])
def api_save_model_settings(model_name):
    try:
        if not ollama_service.app:
            ollama_service.init_app(current_app)
        payload = request.get_json() or {}
        success = ollama_service.save_model_settings(model_name, payload, source='user')
        if success:
            return _json_success(f"Settings for {model_name} saved.")
        return _json_error(f"Failed to save settings for {model_name}", status=500)
    except Exception as e:
        return _json_error(f"Unexpected error saving model settings: {str(e)}")


@bp.route('/api/models/settings/<model_name>', methods=['DELETE'])
def api_delete_model_settings(model_name):
    try:
        if not ollama_service.app:
            ollama_service.init_app(current_app)
        success = ollama_service.delete_model_settings(model_name)
        if success:
            return _json_success(f"Settings for {model_name} deleted.")
        return _json_error(f"Settings for {model_name} not found.", status=404)
    except Exception as e:
        return _json_error(f"Unexpected error deleting model settings: {str(e)}")


@bp.route('/api/models/settings/migrate', methods=['POST'])
def api_migrate_model_settings():
    try:
        if not ollama_service.app:
            ollama_service.init_app(current_app)
        return _json_error("Global settings migration no longer supported", status=410)
    except Exception as e:
        return _json_error(f"Migration error: {str(e)}")


@bp.route('/api/models/settings/apply_all_recommended', methods=['POST'])
def api_apply_all_recommended():
    try:
        if not ollama_service.app:
            ollama_service.init_app(current_app)
        models = ollama_service.get_available_models()
        applied = 0
        errors = []
        for m in models:
            try:
                name = m.get('name')
                rec = ollama_service._recommend_settings_for_model(m)
                if rec:
                    success = ollama_service.save_model_settings(name, rec, source='recommended')
                    if success:
                        applied += 1
            except Exception as e:
                errors.append(str(e))
        return _json_success(f"Applied recommended settings to {applied} models.", extra={'applied': applied, 'errors': errors})
    except Exception as e:
        return _json_error(f"Error applying all recommended settings: {str(e)}")


@bp.route('/api/models/settings/<model_name>/reset', methods=['POST'])
def api_reset_model_settings(model_name):
    try:
        if not ollama_service.app:
            ollama_service.init_app(current_app)
        # Compute recommended settings
        recommended = ollama_service._recommend_settings_for_model(ollama_service.get_model_info_cached(model_name) or {'name': model_name})
        # Save as recommended (not user)
        success = ollama_service.save_model_settings(model_name, recommended, source='recommended')
        if success:
            return _json_success(f"Settings for {model_name} reset to recommended defaults.")
        return _json_error(f"Failed to reset settings for {model_name}", status=500)
    except Exception as e:
        return _json_error(f"Unexpected error resetting model settings: {str(e)}")


@bp.route('/api/version')
def get_ollama_version():
    """Get Ollama version."""
    try:
        version = ollama_service.get_ollama_version()
        return {"version": version}
    except Exception as e:
        return {"error": str(e), "version": "Unknown"}, 500


@bp.route('/api/models/bulk/start', methods=['POST'])
def bulk_start_models():
    """Start multiple models in bulk."""
    try:
        data = request.get_json()
        model_names = data.get('models', [])
        results = []

        for model_name in model_names:
            try:
                response = requests.post(
                    _get_ollama_url("generate"),
                    json={"model": model_name, "prompt": "Hello", "stream": False},
                    timeout=10
                )
                results.append({
                    "model": model_name,
                    "success": response.status_code == 200,
                    "error": response.text if response.status_code != 200 else None
                })
            except Exception as e:
                results.append({"model": model_name, "success": False, "error": str(e)})

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
        if not ollama_service.get_model_info_cached(model_name):
            return {"error": f"Model '{model_name}' not found. Please ensure it's installed."}, 404

        chat_data = {
            "model": model_name,
            "prompt": prompt,
            "stream": stream
        }
        if context:
            chat_data["context"] = context

        # Use service defaults then merge per-model recommended/ saved settings (global settings removed)
        options = ollama_service.get_default_settings()
        # Merge per-model settings (fallback recommended if no saved entry)
        try:
            model_settings_entry = ollama_service.get_model_settings_with_fallback(model_name)
            if model_settings_entry and isinstance(model_settings_entry.get('settings'), dict):
                for k, v in model_settings_entry['settings'].items():
                    options[k] = v
        except Exception as e:
            print(f"Failed to merge per-model settings for {model_name}: {e}")
        chat_data["options"] = options

        try:
            response = requests.post(
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
    """Delete a model from the system."""
    try:
        if not ollama_service.app:
            ollama_service.init_app(current_app)

        # Stop model if running
        running_models = ollama_service.get_running_models()
        if any(model['name'] == model_name for model in running_models):
            try:
                requests.post(
                    _get_ollama_url("generate"),
                    json={"model": model_name, "prompt": "", "stream": False, "keep_alive": "0s"},
                    timeout=10
                )
                time.sleep(2)  # Wait for unload
            except Exception:
                return {"success": False, "message": f"Failed to stop running model '{model_name}' before deletion."}, 400

        # Check if model exists
        available_models = ollama_service.get_available_models()
        if not any(model['name'] == model_name for model in available_models):
            return {"success": False, "message": f"Model '{model_name}' not found in available models."}, 404

        # Delete the model
        try:
            response = requests.delete(
                _get_ollama_url("delete"),
                json={"name": model_name},
                timeout=30
            )
            if response.status_code == 200:
                return {"success": True, "message": f"Model '{model_name}' deleted successfully."}, 200
            return {"success": False, "message": f"Failed to delete model: {response.text}"}, response.status_code or 500
        except requests.exceptions.Timeout:
            return {"success": False, "message": "Model deletion timed out."}, 408

    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500


@bp.route('/api/models/status/<model_name>')
def get_model_status(model_name):
    """Get the status of a specific model."""
    try:
        running_models = ollama_service.get_running_models()
        if any(model['name'] == model_name for model in running_models):
            return {"status": "running", "ready": True}

        available_models = ollama_service.get_available_models()
        if any(model['name'] == model_name for model in available_models):
            return {"status": "available", "ready": False, "message": "Model is installed but not loaded."}

        return {"status": "not_found", "ready": False, "message": "Model is not installed."}

    except Exception as e:
        return {"status": "error", "ready": False, "error": str(e)}, 500


@bp.route('/api/chat/history', methods=['GET'])
def get_chat_history():
    """Get chat history."""
    try:
        history = ollama_service.get_chat_history()
        return {"history": history}
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/chat/history', methods=['POST'])
def save_chat_history():
    """Save a chat session."""
    try:
        data = request.get_json()
        ollama_service.save_chat_session(data)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/performance/<model_name>')
def get_model_performance(model_name):
    """Get performance metrics for a model."""
    try:
        performance = ollama_service.get_model_performance(model_name)
        return performance
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/system/stats/history')
def get_system_stats_history():
    """Get historical system statistics."""
    try:
        history = ollama_service.get_system_stats_history()
        return {"history": history}
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/service/status')
def get_service_status():
    """Get Ollama service status."""
    try:
        status = ollama_service.get_service_status() or False
        return {"status": "running" if status else "stopped", "running": status}
    except Exception as e:
        return {"error": str(e), "status": "unknown", "running": False}, 500

@bp.route('/api/health')
def api_health():
    """Component health: background thread, cache ages, failure counters."""
    try:
        if not ollama_service.app:
            ollama_service.init_app(current_app)
        return ollama_service.get_component_health()
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route('/api/service/start', methods=['POST'])
def start_service():
    """Start the Ollama service."""
    try:
        result = ollama_service.start_service() or {}
        if not result:
            return {"success": False, "message": "Service start returned no result"}, 500
        return (result, 200) if isinstance(result, dict) and result.get("success") else (result, 500)
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500


@bp.route('/api/service/stop', methods=['POST'])
def stop_service():
    """Stop the Ollama service."""
    try:
        result = ollama_service.stop_service()
        return (result, 200) if isinstance(result, dict) and result.get("success") else (result, 500)
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500


@bp.route('/api/service/restart', methods=['POST'])
def restart_service():
    """Restart the Ollama service."""
    try:
        result = ollama_service.restart_service()
        return (result, 200) if isinstance(result, dict) and result.get("success") else (result, 500)
    except Exception as e:
        return {"success": False, "message": f"Unexpected error restarting service: {str(e)}"}, 500

@bp.route('/api/full/restart', methods=['POST'])
def full_restart():
    """Perform comprehensive application restart (caches + settings + background thread). Does NOT restart Ollama service."""
    try:
        result = ollama_service.full_restart()
        return (result, 200) if result.get("success") else (result, 500)
    except Exception as e:
        return {"success": False, "message": f"Unexpected error performing full restart: {str(e)}"}, 500


@bp.route('/api/models/memory/usage')
def get_models_memory_usage():
    """Get memory usage information for running models."""
    try:
        if not ollama_service.app:
            ollama_service.init_app(current_app)

        memory_usage = ollama_service.get_models_memory_usage()
        return memory_usage if memory_usage else ({"error": "Memory monitoring not available"}, 503)
    except Exception as e:
        return {"error": str(e)}, 500



@bp.route('/api/models/pull/<model_name>', methods=['POST'])
def pull_model(model_name):
    """Pull a model."""
    try:
        result = ollama_service.pull_model(model_name)
        if isinstance(result, dict) and result.get("success"):
            return result, 200
        return result if isinstance(result, dict) else {"success": False, "message": str(result)}, 500
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500


@bp.route('/api/models/downloadable')
def api_get_downloadable_models():
    """Get list of downloadable models."""
    try:
        category = request.args.get('category', 'best')
        print(f"DEBUG ROUTE: category parameter = '{category}'")
        models = ollama_service.get_downloadable_models(category)
        print(f"DEBUG ROUTE: got {len(models)} models")
        return {"models": models}
    except Exception as e:
        return {"error": str(e), "models": []}, 500


def _json_error(message, status=500):
    return jsonify({"success": False, "message": message}), status

def _json_success(message, extra=None, status=200):
    payload = {"success": True, "message": message}
    if extra:
        payload.update(extra)
    return jsonify(payload), status

@bp.route('/api/models/pull/<model_name>', methods=['POST'])
def api_pull_model(model_name):
    """Pull a model with standardized JSON response."""
    try:
        result = ollama_service.pull_model(model_name)
        if result.get("success"):
            return _json_success(result.get("message", f"Pulled {model_name}"))
        return _json_error(result.get("message", "Failed to pull model"))
    except Exception as e:
        return _json_error(f"Unexpected error pulling model: {str(e)}")


# Removed duplicate warm-load start_model route; unified logic provided earlier with endpoint 'api_start_model'.


@bp.route('/api/test-models-debug')
def test_models_debug():
    """Test endpoint to debug model counts."""
    best = ollama_service.get_best_models()
    all_models = ollama_service.get_all_downloadable_models()
    best_via_method = ollama_service.get_downloadable_models('best')
    all_via_method = ollama_service.get_downloadable_models('all')

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
    try:
        if not ollama_service.app:
            ollama_service.init_app(current_app)
        return render_template('admin_model_defaults.html')
    except Exception as e:
        return render_template('admin_model_defaults.html')


# Global /api/settings endpoint removed (legacy global settings deprecated).


@bp.route('/api/health')
def get_health():
    """Production health monitoring endpoint."""
    try:
        if not ollama_service.app:
            ollama_service.init_app(current_app)

        # Calculate uptime
        start_time = current_app.config.get('START_TIME')
        uptime_seconds = 0
        if start_time:
            uptime_seconds = int((datetime.utcnow() - start_time).total_seconds())

        # Get model counts
        running_models = ollama_service.get_running_models()
        available_models = ollama_service.get_available_models()

        # Get system stats
        system_stats = ollama_service.get_system_stats()

        # Check Ollama service status
        ollama_running = ollama_service.get_service_status() or False

        status = "healthy" if ollama_running and system_stats else ("degraded" if ollama_running else "unhealthy")
        return {
            "status": status,
            "uptime_seconds": uptime_seconds,
            "ollama_service_running": ollama_running,
            "models": {
                "running_count": len(running_models),
                "available_count": len(available_models),
                "per_model_metrics_available": False
            },
            "system": {
                "cpu_percent": system_stats.get('cpu_percent', 0) if system_stats else 0,
                "memory_percent": system_stats.get('memory', {}).get('percent', 0) if system_stats else 0,
                "vram_percent": system_stats.get('vram', {}).get('percent', 0) if system_stats and system_stats.get('vram', {}).get('total', 0) > 0 else None,
                "disk_percent": system_stats.get('disk', {}).get('percent', 0) if system_stats else 0
            },
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }, 503


def init_app(app):
    """Initialize the blueprint with the app."""
    ollama_service.init_app(app)
    # Template filters (`datetime` and `time_ago`) are registered in app factory via app.__init__.
    # Avoid duplicate registration here to prevent platform-specific filter overrides.
