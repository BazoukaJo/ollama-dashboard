"""Round-trip tests for Ask? saved chat history API."""
import json

from app import create_app
from app.services.ollama import OllamaService


def _client_with_history(tmp_path):
    app = create_app()
    client = app.test_client()
    svc = OllamaService()
    svc.init_app(app)
    app.config["HISTORY_FILE"] = str(tmp_path / "history.json")
    return client, app


def test_chat_history_save_get_delete_round_trip(tmp_path):
    client, _app = _client_with_history(tmp_path)

    payload = {
        "model": "llama3.2:3b",
        "prompt": "What is Ollama?",
        "response": "Ollama runs LLMs locally.",
        "attachments": [{"type": "pdf", "name": "notes.pdf"}],
    }
    save_resp = client.post(
        "/api/chat/history",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert save_resp.status_code == 200
    save_data = save_resp.get_json()
    assert save_data.get("success") is True
    session_id = save_data.get("id")
    assert session_id

    get_resp = client.get("/api/chat/history")
    assert get_resp.status_code == 200
    history = get_resp.get_json().get("history") or []
    assert len(history) == 1
    assert history[0]["id"] == session_id
    assert history[0]["model"] == "llama3.2:3b"
    assert history[0]["prompt"] == "What is Ollama?"
    assert history[0]["response"] == "Ollama runs LLMs locally."
    assert history[0]["attachments"] == [{"type": "pdf", "name": "notes.pdf"}]
    assert history[0].get("timestamp")

    del_resp = client.delete(f"/api/chat/history/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.get_json().get("success") is True

    get_resp2 = client.get("/api/chat/history")
    assert get_resp2.status_code == 200
    assert get_resp2.get_json().get("history") == []


def test_chat_history_clear_all(tmp_path):
    client, _app = _client_with_history(tmp_path)

    for i in range(2):
        client.post(
            "/api/chat/history",
            data=json.dumps(
                {
                    "model": "mistral",
                    "prompt": f"Question {i}",
                    "response": f"Answer {i}",
                }
            ),
            content_type="application/json",
        )

    get_resp = client.get("/api/chat/history")
    assert len(get_resp.get_json().get("history") or []) == 2

    clear_resp = client.delete("/api/chat/history")
    assert clear_resp.status_code == 200
    assert clear_resp.get_json().get("success") is True

    get_resp2 = client.get("/api/chat/history")
    assert get_resp2.get_json().get("history") == []


def test_chat_history_save_validation(tmp_path):
    client, _app = _client_with_history(tmp_path)

    missing_model = client.post(
        "/api/chat/history",
        data=json.dumps({"prompt": "hi", "response": "there"}),
        content_type="application/json",
    )
    assert missing_model.status_code == 400

    empty_exchange = client.post(
        "/api/chat/history",
        data=json.dumps({"model": "llama3"}),
        content_type="application/json",
    )
    assert empty_exchange.status_code == 400


def test_chat_history_delete_not_found(tmp_path):
    client, _app = _client_with_history(tmp_path)

    resp = client.delete("/api/chat/history/does-not-exist")
    assert resp.status_code == 404


def test_chat_history_assigns_ids_to_legacy_entries(tmp_path):
    client, app = _client_with_history(tmp_path)
    chat_file = tmp_path / "chat_history.json"
    chat_file.write_text(
        json.dumps(
            [
                {
                    "model": "legacy",
                    "prompt": "old question",
                    "response": "old answer",
                    "timestamp": "2020-01-01T00:00:00",
                }
            ]
        ),
        encoding="utf-8",
    )

    svc = app.config["OLLAMA_SERVICE"]
    history = svc.get_chat_history()
    assert len(history) == 1
    assert history[0].get("id")

    get_resp = client.get("/api/chat/history")
    assert get_resp.status_code == 200
    items = get_resp.get_json().get("history") or []
    assert len(items) == 1
    assert items[0].get("id")
