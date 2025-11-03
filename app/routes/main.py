"""
Main routes for Ollama Dashboard.
"""
import os
import time
import requests
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
                             ollama_version=version)
    except Exception as e:
        return render_template('index.html',
                             models=[],
                             available_models=[],
                             system_stats={'cpu_percent': 0, 'memory': {'percent': 0}, 'vram': {'percent': 0}, 'disk': {'percent': 0}},
                             error=str(e),
                             timezone=_get_timezone_name(),
                             ollama_version='Unknown')

@bp.route('/api/test')
def test():
    return {"message": "API is working"}

def _get_ollama_url(endpoint=""):
    """Generate Ollama API URL."""
    host = ollama_service.app.config.get('OLLAMA_HOST')
    port = ollama_service.app.config.get('OLLAMA_PORT')
    return f"http://{host}:{port}/api/{endpoint}"


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


@bp.route('/api/models/start/<model_name>', methods=['POST'])
def start_model(model_name):
    """
    Start a model by loading it into memory.

    Attempts to generate with the model first, and if that fails,
    tries to pull the model from the registry before loading.
    """
    try:
        # Check if model is already running
        running_models = ollama_service.get_running_models()
        if any(model['name'] == model_name for model in running_models):
            return {"success": True, "message": f"Model {model_name} is already running"}

        # Check if Ollama service is running
        if not ollama_service.get_service_status():
            return {"success": False, "message": "Ollama service is not running. Please start the service first."}, 503

        # Try to generate with the model to load it
        try:
            response = requests.post(
                _get_ollama_url("generate"),
                json={"model": model_name, "prompt": "Hello", "stream": False, "keep_alive": "24h"},
                timeout=30
            )

            if response.status_code == 200:
                return {"success": True, "message": f"Model {model_name} started successfully"}

            # Handle specific errors
            error_result, status_code = _handle_model_error(response, model_name, "start")
            if error_result["success"] is False:
                # Try to pull the model first, then generate
                try:
                    pull_response = requests.post(
                        _get_ollama_url("pull"),
                        json={"name": model_name, "stream": False},
                        timeout=300
                    )

                    if pull_response.status_code == 200:
                        # Try to generate again after pulling
                        gen_response = requests.post(
                            _get_ollama_url("generate"),
                            json={"model": model_name, "prompt": "Hello", "stream": False, "keep_alive": "24h"},
                            timeout=30
                        )

                        if gen_response.status_code == 200:
                            return {"success": True, "message": f"Model {model_name} downloaded and started successfully"}

                        error_result, status_code = _handle_model_error(gen_response, model_name, "start after download")
                        return error_result, status_code
                    else:
                        return {"success": False, "message": f"Failed to download model: {pull_response.text}"}, 400

                except requests.exceptions.Timeout:
                    return {"success": False, "message": "Model download timed out. The model might be too large."}, 408

        except requests.exceptions.Timeout:
            return {"success": False, "message": "Model loading timed out. Try a smaller model."}, 408
        except requests.exceptions.ConnectionError:
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

        # First try to unload the model gracefully using Ollama API
        try:
            unload_response = requests.post(
                f"http://{ollama_service.app.config.get('OLLAMA_HOST')}:{ollama_service.app.config.get('OLLAMA_PORT')}/api/generate",
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
            # Find Ollama processes
            ollama_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] and 'ollama' in proc.info['name'].lower():
                        ollama_processes.append(proc)
                    elif proc.info['cmdline'] and any('ollama' in str(cmd).lower() for cmd in proc.info['cmdline']):
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
            return ({"success": True, "message": f"Model '{model_name}' deleted successfully."}
                   if response.status_code == 200
                   else {"success": False, "message": f"Failed to delete model: {response.text}"}, 500)
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
        status = ollama_service.get_service_status()
        return {"status": "running" if status else "stopped", "running": status}
    except Exception as e:
        return {"error": str(e), "status": "unknown", "running": False}, 500


@bp.route('/api/service/start', methods=['POST'])
def start_service():
    """Start the Ollama service."""
    try:
        result = ollama_service.start_service()
        return (result, 200) if result["success"] else (result, 500)
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500


@bp.route('/api/service/stop', methods=['POST'])
def stop_service():
    """Stop the Ollama service."""
    try:
        result = ollama_service.stop_service()
        return (result, 200) if result["success"] else (result, 500)
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500


@bp.route('/api/service/restart', methods=['POST'])
def restart_service():
    """Restart the Ollama service."""
    try:
        result = ollama_service.restart_service()
        return (result, 200) if result["success"] else (result, 500)
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500



def init_app(app):
    """Initialize the blueprint with the app."""
    ollama_service.init_app(app)
    app.template_filter('datetime')(ollama_service.format_datetime)
    app.template_filter('time_ago')(ollama_service.format_time_ago)
