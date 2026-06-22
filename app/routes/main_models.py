"""Model management API routes for the main blueprint."""
from __future__ import annotations

import json
import time

import requests
from flask import Response, current_app, jsonify, request, stream_with_context

import app.routes.main as main_routes
from app.routes import bp
from app.routes.main import (
    _ROUTE_ERRORS,
    _force_unload_via_ollama_restart,
    _get_ollama_url,
    _handle_model_error,
    _json_error,
    _json_success,
    _models_force_refresh,
    _rate_limit_response,
    _resolve_model_name,
    _validate_model_name,
)
from app.services.model_helpers import (
    attach_last_token_usage_to_model,
    attach_request_context_to_model,
)
from app.services.model_settings_helpers import (
    compute_fresh_recommended_settings_entry,
    get_existing_model_settings_entry,
)
from app.services.performance import timed_operation
from app.services.validators import InputValidator
from app.services.warm_start import build_warm_start_payload


@bp.route('/api/models/start/<model_name>', methods=['POST'], endpoint='api_start_model')
@bp.route('/api/models/start', methods=['POST'], endpoint='api_start_model_qp')
def start_model(model_name=None):
    """
    Start a model by loading it into memory.

    Attempts to generate with the model first, and if that fails,
    tries to pull the model from the registry before loading.
    Retries up to 3 times for transient connection errors (forcibly closed).
    """
    model_name, err_resp = _resolve_model_name(model_name)
    if err_resp:
        return err_resp
    limited = _rate_limit_response('model_operations')
    if limited:
        return limited
    try:
        running_models = main_routes._get_ollama_service().get_running_models(force_refresh=True)
        if any(model['name'] == model_name for model in running_models):
            return {"success": True, "message": f"Model {model_name} is already running"}

        if not main_routes._get_ollama_service().get_service_status():
            return {"success": False, "message": "Ollama service is not running. Please start the service first."}, 503

        def _is_transient_error(error_text):
            """Check if error is transient (connection forcibly closed, etc.)"""
            return main_routes._get_ollama_service().is_transient_error(error_text)

        def _attempt_generate(retry_num=0, max_retries=3, timeout=60):
            """Attempt to generate with retry logic for transient errors.

            Args:
                retry_num: Current retry attempt (0-indexed)
                max_retries: Maximum number of retries (3)
                timeout: Request timeout in seconds (60s base, increases on retry)
            """
            # Avoid unbounded timeout growth across retries.
            timeout = min(int(timeout), 120)

            warm_payload = build_warm_start_payload(main_routes._get_ollama_service(), model_name)

            try:
                response = main_routes._get_ollama_service()._session.post(
                    _get_ollama_url("generate"),
                    json=warm_payload,
                    timeout=timeout
                )

                if response.status_code == 200:
                    try:
                        main_routes._get_ollama_service().record_model_activity(model_name)
                    except _ROUTE_ERRORS:
                        pass
                    return {"success": True, "response": response}

                error_text = response.text
                try:
                    error_json = response.json()
                    if 'error' in error_json:
                        error_text = error_text + " " + str(error_json['error'])
                except _ROUTE_ERRORS:
                    pass

                current_app.logger.debug(f"Attempt {retry_num + 1}/{max_retries + 1}: Response status {response.status_code}")
                current_app.logger.debug(f"Error text: {error_text[:200]}")  # First 200 chars
                current_app.logger.debug(f"Is transient: {_is_transient_error(error_text)}")

                if _is_transient_error(error_text) and retry_num < max_retries:
                    wait_time = 2 ** retry_num  # Exponential backoff: 1s, 2s, 4s
                    current_app.logger.debug(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    return _attempt_generate(retry_num + 1, max_retries, min(timeout + 30, 120))  # Increase timeout on retry

                return {"success": False, "response": response}

            except requests.exceptions.Timeout:
                if retry_num < max_retries:
                    time.sleep(2)
                    return _attempt_generate(retry_num + 1, max_retries, min(timeout + 30, 120))
                raise
            except requests.exceptions.ConnectionError as e:
                if _is_transient_error(str(e)) and retry_num < max_retries:
                    time.sleep(2 ** retry_num)
                    return _attempt_generate(retry_num + 1, max_retries, min(timeout + 30, 120))
                raise

        try:
            result = _attempt_generate()

            if result["success"]:
                try:
                    main_routes._get_ollama_service().record_model_token_usage_from_response(
                        model_name, result["response"]
                    )
                except _ROUTE_ERRORS:
                    pass
                main_routes._get_ollama_service().clear_cache('running_models')
                try:
                    main_routes._get_ollama_service().get_running_models(force_refresh=True)
                except _ROUTE_ERRORS:
                    pass
                return {"success": True, "message": f"Model {model_name} started successfully"}

            error_result, status_code = _handle_model_error(result["response"], model_name, "start")
            if error_result["success"] is False:
                try:
                    pull_response = main_routes._get_ollama_service()._session.post(
                        _get_ollama_url("pull"),
                        json={"name": model_name, "stream": False},
                        timeout=600
                    )

                    if pull_response.status_code == 200:
                        # Try to generate again after pulling with retry logic
                        result = _attempt_generate()

                        if result["success"]:
                            try:
                                main_routes._get_ollama_service().record_model_token_usage_from_response(
                                    model_name, result["response"]
                                )
                            except _ROUTE_ERRORS:
                                pass
                            # Clear the cache for running models to force a refresh
                            main_routes._get_ollama_service().clear_cache('running_models')
                            # Force immediate refresh to populate cache with current state
                            try:
                                main_routes._get_ollama_service().get_running_models(force_refresh=True)
                            except _ROUTE_ERRORS:
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
            return {"success": False, "message": "Cannot connect to Ollama. Check that the service is running and that OLLAMA_HOST/OLLAMA_PORT (if set) are correct."}, 503

        return {"success": False, "message": f"Failed to start model {model_name}"}, 500

    except _ROUTE_ERRORS as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500

@bp.route('/api/models/stop/<model_name>', methods=['POST'])
@bp.route('/api/models/stop', methods=['POST'], endpoint='api_stop_model_qp')
def stop_model(model_name=None):
    """Unload a model from memory using Ollama API (keep_alive=0).

    Optional JSON body ``{"force": true}`` restarts Ollama to force-clear memory
    when graceful unload fails or the model is stuck.
    """
    model_name, err_resp = _resolve_model_name(model_name)
    if err_resp:
        return err_resp
    limited = _rate_limit_response('model_operations')
    if limited:
        return limited
    try:
        payload = request.get_json(silent=True) or {}
        force = bool(payload.get('force'))
        unpin = bool(payload.get('unpin'))

        from app.services.model_residency import is_pinned, unpin_model

        if unpin:
            unpin_model(model_name)

        if force:
            if not main_routes._get_ollama_service().get_service_status():
                return {"success": False, "message": "Ollama service is not running"}, 503
            running_models = main_routes._get_ollama_service().get_running_models(force_refresh=True)
            if not any(m.get('name') == model_name for m in running_models):
                if is_pinned(model_name):
                    unpin_model(model_name)
                    return {
                        "success": True,
                        "message": f"Model {model_name} was not loaded; removed from pin registry",
                    }
                return {"success": False, "message": f"Model {model_name} is not currently running"}, 400
            result, code = _force_unload_via_ollama_restart(model_name)
            if result.get('success'):
                unpin_model(model_name)
            return result, code

        # Verify Ollama service is running
        if not main_routes._get_ollama_service().get_service_status():
            return {"success": False, "message": "Ollama service is not running"}, 503

        # Check if model is currently running
        running_models = main_routes._get_ollama_service().get_running_models(force_refresh=True)
        if not any(m.get('name') == model_name for m in running_models):
            if is_pinned(model_name):
                unpin_model(model_name)
                return {
                    "success": True,
                    "message": f"Model {model_name} was not loaded; removed from pin registry",
                }
            return {"success": False, "message": f"Model {model_name} is not currently running"}, 400

        if is_pinned(model_name) and not unpin:
            return {
                "success": False,
                "message": (
                    f"Model {model_name} is pinned for RAM residency. "
                    "POST with {\"unpin\": true} to allow unload, or {\"force\": true} to restart Ollama."
                ),
            }, 409

        # Gracefully unload the model using Ollama API
        # Per Ollama docs: empty prompt + keep_alive=0 (numeric) unloads immediately
        try:
            unload_response = main_routes._get_ollama_service()._session.post(
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
                try:
                    body = unload_response.json()
                    if body.get("error"):
                        return {
                            "success": False,
                            "message": f"Ollama error: {body['error']}",
                            "can_force": True,
                        }, 500
                except _ROUTE_ERRORS:
                    pass
                if not main_routes._verify_model_unloaded(model_name, max_attempts=10, delay_seconds=1):
                    return {
                        "success": False,
                        "message": (
                            f"Model {model_name} may still be loaded. "
                            "Retry with force=true or restart Ollama to force-unload."
                        ),
                        "can_force": True,
                    }, 504
                main_routes._get_ollama_service().clear_cache('running_models')
                try:
                    main_routes._get_ollama_service().get_running_models(force_refresh=True)
                except _ROUTE_ERRORS:
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
                except _ROUTE_ERRORS:
                    pass
                return {
                    "success": False,
                    "message": error_msg,
                    "can_force": True,
                }, int(unload_response.status_code)

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": f"Timeout while stopping model {model_name}. The model may still be unloading.",
                "can_force": True,
            }, 504
        except requests.exceptions.RequestException as e:
            return {"success": False, "message": f"Network error while stopping model: {str(e)}"}, 503

    except _ROUTE_ERRORS as e:
        current_app.logger.error(f"Unexpected error stopping model {model_name}: {str(e)}")
        return {"success": False, "message": f"Unexpected error stopping model: {str(e)}"}, 500


@bp.route('/api/models/restart/<model_name>', methods=['POST'])
@bp.route('/api/models/restart', methods=['POST'], endpoint='api_restart_model_qp')
def restart_model(model_name=None):
    """Restart a model by stopping then starting it.

    Atomically performs stop (if running) followed by warm start.
    If stop fails, does not proceed with start.
    """
    model_name, err_resp = _resolve_model_name(model_name)
    if err_resp:
        return err_resp
    limited = _rate_limit_response('model_operations')
    if limited:
        return limited
    try:
        # Verify Ollama service is running
        if not main_routes._get_ollama_service().get_service_status():
            return {"success": False, "message": "Ollama service is not running"}, 503

        # Check if model is currently running
        running_models = main_routes._get_ollama_service().get_running_models(force_refresh=True)
        is_running = any(m.get('name') == model_name for m in running_models)

        # Step 1: Stop the model if it's running
        if is_running:
            try:
                unload_response = main_routes._get_ollama_service()._session.post(
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
                    except _ROUTE_ERRORS:
                        pass
                    return {"success": False, "message": error_msg}, int(unload_response.status_code)

            except requests.exceptions.Timeout:
                return {"success": False, "message": f"Timeout while stopping model {model_name} during restart"}, 504
            except requests.exceptions.RequestException as e:
                return {"success": False, "message": f"Network error while stopping model: {str(e)}"}, 503

            time.sleep(3)
            main_routes._verify_model_unloaded(model_name)
            main_routes._get_ollama_service().clear_cache('running_models')

        # Step 2: Start the model (warm start with retry logic)
        max_retries = 3
        retry_delay = 1
        last_error = None

        for attempt in range(max_retries):
            try:
                start_payload = build_warm_start_payload(
                    main_routes._get_ollama_service(), model_name, prompt='test',
                )
                start_response = main_routes._get_ollama_service()._session.post(
                    _get_ollama_url("generate"),
                    json=start_payload,
                    timeout=120
                )

                if start_response.status_code == 200:
                    try:
                        main_routes._get_ollama_service().record_model_token_usage_from_response(
                            model_name, start_response
                        )
                    except _ROUTE_ERRORS:
                        pass
                    message = f"Model {model_name} restarted successfully"
                    if attempt > 0:
                        message += f" (after {attempt + 1} attempts)"
                    return {"success": True, "message": message}
                elif start_response.status_code == 404:
                    # Model not found - if first attempt, try pulling it
                    if attempt == 0:
                        current_app.logger.info(f"Model {model_name} not found, attempting to pull")
                        try:
                            pull_response = main_routes._get_ollama_service()._session.post(
                                _get_ollama_url("pull"),
                                json={"name": model_name},
                                timeout=600
                            )
                            if pull_response.status_code == 200:
                                continue  # Retry start after successful pull
                        except _ROUTE_ERRORS as pull_error:
                            current_app.logger.error(f"Failed to pull model: {str(pull_error)}")
                    return {"success": False, "message": f"Model {model_name} not found"}, 404
                else:
                    last_error = f"HTTP {start_response.status_code}"
                    try:
                        error_detail = start_response.json().get('error', '')
                        if error_detail:
                            last_error += f" - {error_detail}"
                    except _ROUTE_ERRORS:
                        pass

                    # Check if this is a transient error worth retrying
                    if start_response.status_code in [500, 502, 503, 504] and attempt < max_retries - 1:
                        time.sleep(min(retry_delay * (2 ** attempt), 32))  # Exponential backoff with cap
                        continue
                    return {"success": False, "message": f"Failed to restart model: {last_error}"}, start_response.status_code

            except requests.exceptions.Timeout:
                last_error = "Timeout"
                if attempt < max_retries - 1:
                    time.sleep(min(retry_delay * (2 ** attempt), 32))
                    continue
                return {"success": False, "message": f"Timeout while restarting model {model_name}"}, 504
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    time.sleep(min(retry_delay * (2 ** attempt), 32))
                    continue
                return {"success": False, "message": f"Network error while restarting model: {str(e)}"}, 503

        return {"success": False, "message": f"Failed to restart model after {max_retries} attempts: {last_error}"}, 500

    except _ROUTE_ERRORS as e:
        current_app.logger.error(f"Unexpected error restarting model {model_name}: {str(e)}")
        return {"success": False, "message": f"Unexpected error restarting model: {str(e)}"}, 500


@bp.route('/api/models/info/<model_name>')
def get_model_info(model_name):
    """Get detailed information about a specific model."""
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status or 400
    try:
        svc = main_routes._get_ollama_service()
        info = svc.get_model_info_cached(model_name)
        if info:
            return info
        detailed = svc.get_detailed_model_info(model_name)
        if detailed:
            return detailed
        return {"error": "Model not found"}, 404
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/available')
def get_available_models():
    """Get list of all available models."""
    try:
        svc = main_routes._get_ollama_service()
        with timed_operation(getattr(svc, 'performance_metrics', None), 'models_available'):
            models = svc.get_available_models(force_refresh=_models_force_refresh())
        try:
            current_app.logger.debug(
                "[models.available] count=%d names=%s",
                len(models),
                [m.get('name') for m in models],
            )
        except _ROUTE_ERRORS:
            # Logging should never break the endpoint
            pass
        svc = main_routes._get_ollama_service()
        svc.refresh_model_settings_cache_from_disk()
        for m in models:
            m['has_custom_settings'] = svc.has_custom_model_settings(m.get('name'))
            attach_request_context_to_model(svc, m)
            attach_last_token_usage_to_model(svc, m)
        return {"models": models}
    except _ROUTE_ERRORS as e:
        return {"error": str(e), "models": []}, 500


@bp.route('/api/models/derived')
def get_derived_models():
    """Return available models created by 'Bake into Model' (base name ends in -dashboard)."""
    try:
        models = main_routes._get_ollama_service().get_available_models()
        derived = [m for m in models if (m.get('name') or '').split(':')[0].endswith('-dashboard')]
        return {"models": derived}
    except _ROUTE_ERRORS as e:
        return {"models": [], "error": str(e)}, 500


@bp.route('/api/models/running')
def get_running_models():
    """Get list of currently running models."""
    try:
        svc = main_routes._get_ollama_service()
        with timed_operation(getattr(svc, 'performance_metrics', None), 'models_running'):
            models = svc.get_running_models(force_refresh=_models_force_refresh())
        svc.refresh_model_settings_cache_from_disk()
        for m in models or []:
            m['has_custom_settings'] = svc.has_custom_model_settings(m.get('name'))
        try:
            current_app.logger.debug(
                "[models.running] count=%d names=%s",
                len(models),
                [m.get('name') for m in models],
            )
        except _ROUTE_ERRORS:
            # Logging should never break the endpoint
            pass
        return {"models": list(models) if models is not None else []}
    except _ROUTE_ERRORS as e:
        return {"error": str(e), "models": []}, 500


@bp.route('/api/models/lists')
def get_model_lists():
    """Running and available model lists in one request (same shape as separate endpoints)."""
    try:
        svc = main_routes._get_ollama_service()
        force = _models_force_refresh()
        with timed_operation(getattr(svc, 'performance_metrics', None), 'models_lists'):
            running = svc.get_running_models(force_refresh=force)
            available = svc.get_available_models(force_refresh=force)
        svc.refresh_model_settings_cache_from_disk()
        for m in running or []:
            m['has_custom_settings'] = svc.has_custom_model_settings(m.get('name'))
            attach_request_context_to_model(svc, m)
            attach_last_token_usage_to_model(svc, m)
        for m in available or []:
            m['has_custom_settings'] = svc.has_custom_model_settings(m.get('name'))
            attach_request_context_to_model(svc, m)
            attach_last_token_usage_to_model(svc, m)
        return {"running": list(running or []), "available": list(available or [])}
    except _ROUTE_ERRORS as e:
        return {"error": str(e), "running": [], "available": []}, 500


@bp.route('/api/models/combined')
def get_combined_models():
    """
    Return one entry per model name with both availability and running state.

    Shape:
    {
      "models": [
        {
          "name": "deepseek-r1:8b",
          "is_available": true,
          "is_running": true,
          "has_custom_settings": false,
          "available_info": {...},   # from available list when present
          "running_info": {...}      # from running list when present
        },
        ...
      ]
    }
    """
    try:
        svc = main_routes._get_ollama_service()
        available = svc.get_available_models()
        running = svc.get_running_models(force_refresh=_models_force_refresh())
        svc.refresh_model_settings_cache_from_disk()

        by_name = {}

        # Merge available (installed) models
        for model in available:
            name = model.get('name')
            if not name:
                continue
            if name not in by_name:
                by_name[name] = {
                    'name': name,
                    'is_available': False,
                    'is_running': False,
                    'has_custom_settings': False,
                }
            entry = by_name[name]
            entry['is_available'] = True
            entry['available_info'] = model
            # Prefer details from available list for display
            if 'details' not in entry and isinstance(model.get('details'), dict):
                entry['details'] = model.get('details') or {}
            try:
                entry['has_custom_settings'] = bool(
                    svc.has_custom_model_settings(name)
                )
            except _ROUTE_ERRORS:
                # If settings lookup fails, leave flag at default
                pass

        # Merge running (loaded in memory) models
        for model in running:
            name = model.get('name')
            if not name:
                continue
            if name not in by_name:
                by_name[name] = {
                    'name': name,
                    'is_available': False,
                    'is_running': False,
                    'has_custom_settings': False,
                }
            entry = by_name[name]
            entry['is_running'] = True
            entry['running_info'] = model
            if 'details' not in entry and isinstance(model.get('details'), dict):
                entry['details'] = model.get('details') or {}

        return {"models": list(by_name.values())}
    except _ROUTE_ERRORS as exc:
        return {"error": str(exc), "models": []}, 500


@bp.route('/api/models/settings/<model_name>')
@bp.route('/api/models/settings', endpoint='api_get_model_settings_qp')
def api_get_model_settings(model_name=None):
    model_name, err_resp = _resolve_model_name(model_name)
    if err_resp:
        return err_resp
    try:
        data = main_routes._get_ollama_service().get_model_settings_with_fallback(model_name)
        if data is None:
            return {"error": f"Settings not available for model {model_name}"}, 404
        from app.services.copilot_extras import attach_client_to_api_entry
        return attach_client_to_api_entry(data)
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/settings/recommended/<model_name>')
@bp.route('/api/models/settings/recommended', endpoint='api_get_recommended_settings_qp')
def api_get_recommended_settings(model_name=None):
    model_name, err_resp = _resolve_model_name(model_name)
    if err_resp:
        return err_resp
    try:
        data = compute_fresh_recommended_settings_entry(main_routes._get_ollama_service(), model_name)
        if data is None:
            return {"error": f"Settings not available for model {model_name}"}, 404
        return {"model": model_name, "settings": data.get('settings'), "source": data.get('source', 'recommended')}
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/settings/<model_name>', methods=['POST'])
@bp.route('/api/models/settings', methods=['POST'], endpoint='api_save_model_settings_qp')
def api_save_model_settings(model_name=None):
    model_name, err_resp = _resolve_model_name(model_name)
    if err_resp:
        return err_resp
    try:
        payload = request.get_json() or {}
        copilot = payload.pop('copilot', None) if isinstance(payload, dict) else None
        client = payload.pop('client', None) if isinstance(payload, dict) else None
        extras = client or copilot
        success = main_routes._get_ollama_service().save_model_settings(
            model_name, payload, source='user', copilot=extras,
        )
        if success:
            return _json_success(f"Settings for {model_name} saved.")
        return _json_error(f"Failed to save settings for {model_name}", status=500)
    except _ROUTE_ERRORS as e:
        return _json_error(f"Unexpected error saving model settings: {str(e)}")


@bp.route('/api/models/settings/<model_name>', methods=['DELETE'])
@bp.route('/api/models/settings', methods=['DELETE'], endpoint='api_delete_model_settings_qp')
def api_delete_model_settings(model_name=None):
    model_name, err_resp = _resolve_model_name(model_name)
    if err_resp:
        return err_resp
    try:
        success = main_routes._get_ollama_service().delete_model_settings(model_name)
        if success:
            return _json_success(f"Settings for {model_name} deleted.")
        return _json_error(f"Settings for {model_name} not found.", status=404)
    except _ROUTE_ERRORS as e:
        return _json_error(f"Unexpected error deleting model settings: {str(e)}")


@bp.route('/api/models/settings/<model_name>/bake', methods=['POST'])
@bp.route('/api/models/settings/bake', methods=['POST'], endpoint='api_bake_model_settings_qp')
def api_bake_model_settings(model_name=None):
    """Create a derived Ollama model with the dashboard's saved settings baked in
    as Modelfile PARAMETER directives, so external clients (VS Code, `ollama run`,
    etc.) that talk to Ollama directly also get these defaults.
    """
    model_name, err_resp = _resolve_model_name(model_name)
    if err_resp:
        return err_resp
    try:
        result = main_routes._get_ollama_service().bake_model_settings(model_name)
        if result.get('success'):
            return _json_success(result.get('message', f"Baked settings into {result.get('model')}"),
                                 extra={'model': result.get('model')})
        return _json_error(result.get('message', f"Failed to bake settings for {model_name}"), status=500)
    except _ROUTE_ERRORS as e:
        return _json_error(f"Unexpected error baking model settings: {str(e)}")


@bp.route('/api/models/settings/migrate', methods=['POST'])
def api_migrate_model_settings():
    try:
        return _json_error("Global settings migration no longer supported", status=410)
    except _ROUTE_ERRORS as e:
        return _json_error(f"Migration error: {str(e)}")


@bp.route('/api/models/settings/apply_all_recommended', methods=['POST'])
def api_apply_all_recommended():
    try:
        models = main_routes._get_ollama_service().get_available_models()
        svc = main_routes._get_ollama_service()
        applied = 0
        skipped = 0
        errors = []
        for m in models:
            try:
                name = m.get('name')
                if not name:
                    continue
                existing = get_existing_model_settings_entry(svc, name)
                if existing and existing.get('source') == 'user':
                    skipped += 1
                    continue
                fresh = compute_fresh_recommended_settings_entry(svc, name)
                if fresh and fresh.get('settings'):
                    success = svc.save_model_settings(name, fresh['settings'], source='recommended')
                    if success:
                        applied += 1
            except _ROUTE_ERRORS as e:
                errors.append(str(e))
        return _json_success(
            f"Applied recommended settings to {applied} models ({skipped} user-saved skipped).",
            extra={'applied': applied, 'skipped': skipped, 'errors': errors},
        )
    except _ROUTE_ERRORS as e:
        return _json_error(f"Error applying all recommended settings: {str(e)}")


@bp.route('/api/models/settings/copy', methods=['POST'])
def api_copy_model_settings_between():
    """Copy saved/recommended settings from one model name to another."""
    body = request.get_json() or {}
    src = body.get('from') or body.get('source')
    dst = body.get('to') or body.get('target')
    for label, raw in (('source', src), ('target', dst)):
        if not raw or not isinstance(raw, str):
            return {"success": False, "error": f"Missing {label} model name"}, 400
        err, status = _validate_model_name(raw)
        if err is not None:
            return err, status or 400
    if src == dst:
        return _json_error('Source and target must differ', status=400)
    try:
        svc = main_routes._get_ollama_service()
        src_data = svc.get_model_settings_with_fallback(src)
        if not src_data or not isinstance(src_data.get('settings'), dict):
            return _json_error(f"No settings to copy from '{src}'", status=404)
        if not svc.save_model_settings(dst, src_data['settings'], source='user'):
            return _json_error(f"Failed to save settings for '{dst}'", status=500)
        return _json_success(f"Copied settings from '{src}' to '{dst}'.")
    except _ROUTE_ERRORS as exc:
        return _json_error(f"Copy settings failed: {str(exc)}")


@bp.route('/api/models/settings/<model_name>/reset', methods=['POST'])
@bp.route('/api/models/settings/reset', methods=['POST'], endpoint='api_reset_model_settings_qp')
def api_reset_model_settings(model_name=None):
    model_name, err_resp = _resolve_model_name(model_name)
    if err_resp:
        return err_resp
    try:
        # Get recommended settings via fallback
        settings_data = compute_fresh_recommended_settings_entry(main_routes._get_ollama_service(), model_name)
        if not settings_data or not settings_data.get('settings'):
            return _json_error(f"Could not determine recommended settings for {model_name}", status=500)
        # Save as recommended (not user)
        success = main_routes._get_ollama_service().save_model_settings(model_name, settings_data['settings'], source='recommended')
        if success:
            return _json_success(f"Settings for {model_name} reset to recommended defaults.")
        return _json_error(f"Failed to reset settings for {model_name}", status=500)
    except _ROUTE_ERRORS as e:
        return _json_error(f"Unexpected error resetting model settings: {str(e)}")

@bp.route('/api/models/bulk/start', methods=['POST'])
def bulk_start_models():
    """Start multiple models in bulk."""
    limited = _rate_limit_response('model_operations')
    if limited:
        return limited
    try:
        data = request.get_json(silent=True) or {}
        model_names = data.get('models', [])
        if not isinstance(model_names, list):
            model_names = []
        results = []
        svc = main_routes._get_ollama_service()

        for model_name in model_names:
            # Validate each model name individually
            is_valid, msg = InputValidator.validate_model_name(model_name)
            if not is_valid:
                results.append({"model": model_name, "success": False, "error": msg})
                continue
            try:
                bulk_payload = build_warm_start_payload(svc, model_name)
                response = svc._session.post(
                    _get_ollama_url("generate"),
                    json=bulk_payload,
                    timeout=60
                )
                results.append({
                    "model": model_name,
                    "success": response.status_code == 200,
                    "error": None if response.status_code == 200 else 'Model start failed. Check server logs.',
                })
            except _ROUTE_ERRORS as e:
                results.append({"model": model_name, "success": False, "error": str(e)})

        # Invalidate the running-models cache so next GET /api/models/running reflects reality
        svc.clear_cache('running_models')
        return {"results": results}
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500

@bp.route('/api/models/delete/<model_name>', methods=['DELETE'])
@bp.route('/api/models/delete', methods=['DELETE'], endpoint='api_delete_model_qp')
def delete_model(model_name=None):
    """Delete a model and its settings."""
    model_name, err_resp = _resolve_model_name(model_name)
    if err_resp:
        return err_resp
    limited = _rate_limit_response('model_operations')
    if limited:
        return limited
    try:
        svc = main_routes._get_ollama_service()
        # Unload model first if it is running (Ollama may refuse or fail to delete loaded models)
        running_models = svc.get_running_models(force_refresh=True)
        if any(m.get("name") == model_name for m in running_models):
            try:
                svc._session.post(
                    _get_ollama_url("generate"),
                    json={"model": model_name, "prompt": "", "stream": False, "keep_alive": 0},
                    timeout=30,
                )
                main_routes._verify_model_unloaded(model_name)
            except _ROUTE_ERRORS as e:
                current_app.logger.warning("Unload before delete failed: %s", e)

        # Attempt to delete model from Ollama backend
        host, port = svc.get_ollama_host_port()
        url = f"http://{host}:{port}/api/delete"
        response = svc._session.delete(url, json={"name": model_name}, timeout=30)
        if response.status_code != 200:
            try:
                err_json = response.json()
                error_msg = err_json.get("error") or err_json.get("message") or response.text
            except _ROUTE_ERRORS:
                error_msg = response.text
            status_code = int(response.status_code) if response.status_code >= 400 else 400
            return jsonify({"success": False, "message": f"Failed to delete model: {error_msg}"}), status_code

        # Verify model is gone from Ollama
        if not main_routes._verify_model_deleted(model_name):
            return jsonify({"success": False, "message": f"Model '{model_name}' delete was requested but model may still be present."}), 504

        # Remove model settings
        from app.services.model_settings_helpers import delete_model_settings_entry
        settings_deleted = delete_model_settings_entry(svc, model_name)

        # Drop cached model lists/details so the deleted model disappears immediately.
        svc.invalidate_model_catalog(model_name)

        return jsonify({
            "success": True,
            "message": f"Model '{model_name}' deleted successfully. Settings removed: {settings_deleted}"
        }), 200
    except _ROUTE_ERRORS as exc:
        return jsonify({"success": False, "message": f"Exception: {str(exc)}"}), 500


@bp.route('/api/models/performance/<model_name>')
def get_model_performance(model_name):
    """Get performance metrics for a model."""
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status or 400
    try:
        performance = main_routes._get_ollama_service().get_model_performance(model_name)
        return performance
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/benchmark', methods=['POST'])
def benchmark_all_models():
    """Run the benchmark suite on all installed models (slow — may take several minutes)."""
    limited = _rate_limit_response('model_operations')
    if limited:
        return limited
    try:
        body = request.get_json(silent=True) or {}
        raw_names = body.get('models')
        names = None
        if isinstance(raw_names, list):
            names = [str(n).strip() for n in raw_names if str(n).strip()]
        compare_baseline = bool(body.get('compare_baseline') or body.get('compare'))
        async_mode = bool(body.get('async') or body.get('background'))
        if async_mode:
            import concurrent.futures
            from app.services.task_tracker import complete_task, create_task, fail_task, update_task

            models = names
            if not models:
                models = [
                    m.get('name') for m in main_routes._get_ollama_service().get_available_models()
                    if m.get('name')
                ]
            task_id = create_task(
                'benchmark',
                label='Fleet benchmark',
                total_steps=len(models or [1]),
                meta={'compare': compare_baseline, 'models': models},
            )

            def _run() -> None:
                try:
                    update_task(task_id, message='Benchmark running…', step=0)
                    result = main_routes._get_ollama_service().run_all_model_benchmarks(
                        model_names=names,
                        compare_baseline=compare_baseline,
                    )
                    complete_task(task_id, result)
                except _ROUTE_ERRORS as exc:
                    fail_task(task_id, str(exc))

            concurrent.futures.ThreadPoolExecutor(max_workers=1).submit(_run)
            return {'task_id': task_id, 'status': 'running', 'poll': f'/api/tasks/{task_id}'}, 202

        result = main_routes._get_ollama_service().run_all_model_benchmarks(
            model_names=names,
            compare_baseline=compare_baseline,
        )
        return result
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500


@bp.route('/api/tasks')
def list_tasks():
    """Recent long-running task status entries."""
    from app.services.task_tracker import list_tasks as _list_tasks

    return {'tasks': _list_tasks(limit=20)}


@bp.route('/api/tasks/<task_id>')
def get_task_status(task_id):
    """Poll status for async benchmark / tune operations."""
    from app.services.task_tracker import get_task

    task = get_task(task_id)
    if not task:
        return {'error': 'task not found'}, 404
    return task


@bp.route('/api/models/benchmark/tune', methods=['POST'])
def benchmark_tune_loop_route():
    """Start multi-round benchmark → apply → re-test loop (background)."""
    limited = _rate_limit_response('model_operations')
    if limited:
        return limited
    try:
        import concurrent.futures

        from app.services.task_tracker import create_task, fail_task
        from scripts.benchmark_tune_loop import run_tune_loop

        body = request.get_json(silent=True) or {}
        max_rounds = max(1, min(int(body.get('max_rounds') or 3), 5))
        raw_names = body.get('models')
        names = None
        if isinstance(raw_names, list):
            names = [str(n).strip() for n in raw_names if str(n).strip()] or None

        task_id = create_task(
            'benchmark_tune_loop',
            label='Benchmark tune loop',
            total_steps=max_rounds,
            meta={'max_rounds': max_rounds, 'models': names},
        )

        def _run() -> None:
            try:
                run_tune_loop(max_rounds=max_rounds, compare=True, model_names=names, task_id=task_id)
            except Exception as exc:  # noqa: BLE001
                fail_task(task_id, str(exc))

        concurrent.futures.ThreadPoolExecutor(max_workers=1).submit(_run)
        return {
            'status': 'running',
            'task_id': task_id,
            'poll': f'/api/tasks/{task_id}',
            'message': 'Tune loop started — poll task for progress',
        }, 202
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500


@bp.route('/api/models/benchmark/<model_name>', methods=['POST'])
def benchmark_model(model_name):
    """Run the benchmark suite on a single model."""
    err, status = _validate_model_name(model_name)
    if err is not None:
        return err, status or 400
    limited = _rate_limit_response('model_operations')
    if limited:
        return limited
    try:
        body = request.get_json(silent=True) or {}
        if body.get('compare_baseline') or body.get('compare'):
            result = main_routes._get_ollama_service().run_model_benchmark_comparison(model_name)
        else:
            result = main_routes._get_ollama_service().run_model_benchmark(model_name)
        return result
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500


@bp.route('/api/residency/status')
def residency_status():
    """Live pin registry + Ollama /api/ps for multi-model RAM residency."""
    try:
        from app.services.model_residency import get_residency_status

        host, port = main_routes._get_ollama_service()._get_ollama_host_port()
        base = f'http://{host}:{int(port)}'
        return get_residency_status(base)
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500


@bp.route('/api/residency/pin', methods=['POST'])
def residency_pin():
    """Pin a model in Ollama memory (keep_alive). Body: model, role?, keep_alive?, unpin?."""
    limited = _rate_limit_response('model_operations')
    if limited:
        return limited
    try:
        from app.services.model_residency import pin_model_sync, unpin_model

        body = request.get_json(silent=True) or {}
        model_name = str(body.get('model') or '').strip()
        if not model_name:
            return {"success": False, "error": "model required"}, 400
        err, status = _validate_model_name(model_name)
        if err is not None:
            return err, status or 400
        if body.get('unpin'):
            unpin_model(model_name)
            return {"success": True, "unpinned": model_name}
        role = str(body.get('role') or 'custom').strip() or 'custom'
        keep_alive = body.get('keep_alive', -1)
        host, port = main_routes._get_ollama_service()._get_ollama_host_port()
        base = f'http://{host}:{int(port)}'
        result = pin_model_sync(
            main_routes._get_ollama_service(),
            base,
            model_name,
            role=role,
            keep_alive=keep_alive,
        )
        if not result.get('success'):
            return result, 502
        return result
    except _ROUTE_ERRORS as e:
        return {"success": False, "error": str(e)}, 500


@bp.route('/api/models/memory/usage')
def get_models_memory_usage():
    """Get memory usage information for running models."""
    try:
        memory_usage = main_routes._get_ollama_service().get_models_memory_usage()
        return memory_usage if memory_usage else ({"error": "Memory monitoring not available"}, 503)
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500

@bp.route('/api/models/downloadable')
def api_get_downloadable_models():
    """Get list of downloadable models."""
    try:
        category = request.args.get('category', 'best')
        models = main_routes._get_ollama_service().get_downloadable_models(category)
        return {"models": models}
    except _ROUTE_ERRORS as e:
        current_app.logger.error(f"Error in downloadable models endpoint: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 500
@bp.route('/api/models/pull/<model_name>', methods=['POST'])
@bp.route('/api/models/pull', methods=['POST'], endpoint='api_pull_model_qp')
def api_pull_model(model_name=None):
    """Pull a model with optional streaming progress updates."""
    model_name, err_resp = _resolve_model_name(model_name)
    if err_resp:
        return err_resp
    stream = request.args.get('stream', 'false').lower() == 'true'
    try:
        if stream:
            def generate():
                for update in main_routes._get_ollama_service().pull_model_stream(model_name):
                    yield f"data: {json.dumps(update)}\n\n"

            return Response(stream_with_context(generate()), mimetype='text/event-stream')

        result = main_routes._get_ollama_service().pull_model(model_name)
        if isinstance(result, dict) and result.get("success"):
            return _json_success(result.get("message", f"Pulled {model_name}"))
        return _json_error(result.get("message", "Failed to pull model"))
    except _ROUTE_ERRORS as e:
        return _json_error(f"Unexpected error pulling model: {str(e)}")

