"""Chat API routes for the main blueprint."""
from __future__ import annotations

import requests
from flask import Response, current_app, request, stream_with_context

import app.routes.main as main_routes
from app.routes import bp
from app.routes.main import (
    _ROUTE_ERRORS,
    _get_ollama_url,
    _handle_model_error,
    _merge_model_chat_options,
)
from app.services import mcp_tools
from app.services.ask_agent import stream_ask_agent
from app.services.chat_prep import (
    model_has_reasoning as _model_has_reasoning,
)
from app.services.chat_prep import (
    model_has_tools as _model_has_tools,
)
from app.services.chat_prep import (
    prepare_ask_chat_messages,
)
from app.services.validators import InputValidator

# Max JSON payload size for chat history (1MB) to prevent DoS
MAX_CHAT_PAYLOAD_BYTES = 1024 * 1024

@bp.route('/api/chat', methods=['POST'])
def chat():
    """
    Handle chat requests with Ollama models.

    Supports multi-turn ``messages``, streaming, and optional attachments on the latest user turn.
    """
    try:
        data = request.get_json(silent=True) or {}
        model_name = data.get('model')
        stream = data.get('stream', False)

        if not model_name:
            return {"error": "Model name is required"}, 400

        is_valid, msg = InputValidator.validate_model_name(model_name)
        if not is_valid:
            return {"error": msg}, 400

        model_info = main_routes._get_ollama_service().get_model_info_cached(model_name)
        if not model_info:
            return {"error": f"Model '{model_name}' not found. Please ensure it's installed."}, 404

        messages, err_body, err_status = prepare_ask_chat_messages(data, model_info)
        if err_body is not None:
            return err_body, err_status or 400

        chat_data = {
            "model": model_name,
            "messages": messages,
            "stream": stream,
            "options": _merge_model_chat_options(model_name),
        }
        if _model_has_reasoning(model_info):
            chat_data["think"] = True

        try:
            response = main_routes._get_ollama_service()._session.post(
                _get_ollama_url("chat"),
                json=chat_data,
                timeout=120,
                stream=stream,
            )
        except requests.exceptions.Timeout:
            return {"error": "Request timed out. Try a smaller model."}, 408
        except requests.exceptions.ConnectionError:
            return {"error": "Cannot connect to Ollama. Check that the service is running and that OLLAMA_HOST/OLLAMA_PORT (if set) are correct."}, 503

        if response.status_code == 200:
            try:
                main_routes._get_ollama_service().record_model_activity(model_name)
            except _ROUTE_ERRORS:
                pass
            if stream:
                def _generate_stream(r=response):
                    yield from r.iter_content(chunk_size=None)
                return Response(stream_with_context(_generate_stream()), content_type='text/plain')
            try:
                main_routes._get_ollama_service().record_model_token_usage_from_response(
                    model_name, response
                )
            except _ROUTE_ERRORS:
                pass
            return response.json()

        error_result, status_code = _handle_model_error(response, model_name, "chat with")
        return error_result, status_code

    except _ROUTE_ERRORS:
        return {"error": "Unexpected error during chat. Check server logs for details."}, 500


@bp.route('/api/chat/agent', methods=['POST'])
def chat_agent():
    """Ask? agent mode — Ollama /api/chat with dashboard MCP tools (server-side loop)."""
    try:
        data = request.get_json(silent=True) or {}
        model_name = data.get('model')

        if not model_name:
            return {"error": "Model name is required"}, 400

        is_valid, msg = InputValidator.validate_model_name(model_name)
        if not is_valid:
            return {"error": msg}, 400

        model_info = main_routes._get_ollama_service().get_model_info_cached(model_name)
        if not model_info:
            return {"error": f"Model '{model_name}' not found. Please ensure it's installed."}, 404

        if not _model_has_tools(model_info):
            return {
                "error": (
                    f"Model '{model_name}' does not support tools. "
                    "Web search and agent tools require a tool-capable model "
                    "(e.g. qwen3, llama3.2, mistral with tools)."
                ),
            }, 400

        messages, err_body, err_status = prepare_ask_chat_messages(data, model_info)
        if err_body is not None:
            return err_body, err_status or 400

        options = _merge_model_chat_options(model_name)

        allow_write = mcp_tools.mcp_allow_write()
        auth_svc = current_app.config.get('AUTH_SERVICE')
        if auth_svc and allow_write:
            ok, role = auth_svc.authenticate_request(request)
            if not ok or role not in ('operator', 'admin'):
                allow_write = False

        svc = main_routes._get_ollama_service()
        chat_url = _get_ollama_url('chat')

        def _generate():
            try:
                svc.record_model_activity(model_name)
            except _ROUTE_ERRORS:
                pass
            yield from stream_ask_agent(
                session=svc._session,
                chat_url=chat_url,
                model_name=model_name,
                messages=messages,
                options=options,
                allow_write=allow_write,
            )

        return Response(
            stream_with_context(_generate()),
            content_type='application/x-ndjson',
        )
    except _ROUTE_ERRORS:
        return {"error": "Unexpected error during agent chat. Check server logs for details."}, 500

@bp.route('/api/chat/history', methods=['GET'])
def get_chat_history():
    """Get chat history."""
    try:
        history = main_routes._get_ollama_service().get_chat_history()
        return {"history": history}
    except _ROUTE_ERRORS as e:
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
        session_id = main_routes._get_ollama_service().save_chat_session(data or {})
        return {"success": True, "id": session_id}
    except ValueError as e:
        return {"error": str(e)}, 400
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500


@bp.route('/api/chat/history/<session_id>', methods=['DELETE'])
def delete_chat_history_entry(session_id):
    """Delete one saved chat session."""
    try:
        removed = main_routes._get_ollama_service().delete_chat_session(session_id)
        if not removed:
            return {"error": "Session not found"}, 404
        return {"success": True}
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500


@bp.route('/api/chat/history', methods=['DELETE'])
def clear_chat_history():
    """Clear all saved chat sessions."""
    try:
        main_routes._get_ollama_service().clear_chat_history()
        return {"success": True}
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500

