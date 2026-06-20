"""Concurrency stress tests for the OllamaService shared cache + history.

Highest-priority slice: ``_cache`` / ``_cache_timestamps`` are touched by Waitress request
threads, the background stats thread, and the /api/show enrichment pool. Before the
``_cache_lock`` fix these tests reproduce real races:
  * ``clear_cache`` did ``if k in d: del d[k]`` -> TOCTOU ``KeyError`` under concurrent delete,
  * ``_set_cached`` wrote value then timestamp non-atomically -> orphaned value/timestamp,
  * ``get_available_models`` used an instance-wide re-entrancy counter that leaked across threads.

They are probabilistic; thread counts/iterations are tuned to surface a regression quickly while
staying well under a couple of seconds.
"""
import json
import threading

from app.services.ollama import OllamaService


class _StubApp:
    """Minimal stand-in so save_history runs without create_app()/background threads."""

    def __init__(self, history_file):
        self.config = {'HISTORY_FILE': history_file}


def _join_all(threads):
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_cache_concurrent_mutation_is_race_free():
    svc = OllamaService()  # app=None => no init_app, no background thread
    errors: list[str] = []
    stop = threading.Event()
    keys = [f'k{i}' for i in range(8)]

    def writer():
        try:
            while not stop.is_set():
                for k in keys:
                    svc._set_cached(k, {'v': k})
                    svc._get_cached(k, ttl_seconds=10)
                    svc.clear_cache(k)  # concurrent delete of same key => TOCTOU before fix
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(repr(exc))

    def nuker():
        try:
            while not stop.is_set():
                svc.invalidate_model_catalog('m')
                svc.clear_all_caches()
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(repr(exc))

    threads = [threading.Thread(target=writer) for _ in range(6)]
    threads += [threading.Thread(target=nuker) for _ in range(2)]
    for t in threads:
        t.start()
    stop.wait(1.0)
    stop.set()
    for t in threads:
        t.join()

    assert not errors, f"cache operations raced: {errors[:5]}"
    # At quiescence the two dicts must stay in lockstep (atomic set/pop pairs).
    assert set(svc._cache) == set(svc._cache_timestamps)


def test_building_models_depth_is_thread_local():
    svc = OllamaService()
    results: dict[str, int] = {}
    ready = threading.Barrier(2)

    def worker(name, bump):
        ready.wait()
        if bump:
            svc._set_building_models_depth(5)
        # Give the other thread time to observe (it must NOT see our depth).
        threading.Event().wait(0.05)
        results[name] = svc._building_models_depth()

    _join_all([
        threading.Thread(target=worker, args=('bumped', True)),
        threading.Thread(target=worker, args=('other', False)),
    ])

    assert results['bumped'] == 5
    assert results['other'] == 0  # cross-thread isolation


def test_history_concurrent_update_keeps_valid_json(tmp_path):
    hist_file = tmp_path / 'history.json'
    svc = OllamaService()
    svc.app = _StubApp(str(hist_file))
    errors: list[str] = []

    def worker(n):
        try:
            for i in range(60):
                svc.update_history([{'name': f'm{n}-{i}'}])
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(repr(exc))

    _join_all([threading.Thread(target=worker, args=(n,)) for n in range(6)])

    assert not errors, f"history update raced: {errors[:5]}"
    # Atomic rename + per-thread temp file => the final file is always complete valid JSON.
    data = json.loads(hist_file.read_text(encoding='utf-8'))
    assert isinstance(data, list)
    assert len(data) <= 50  # deque(maxlen=50) bound preserved


def test_history_worker_signature(tmp_path):
    """Guard: update_history tolerates the lock being absent (defensive getattr path)."""
    svc = OllamaService()
    svc.app = _StubApp(str(tmp_path / 'h.json'))
    svc._history_lock = None  # simulate older instance without the lock attribute
    svc.update_history([{'name': 'x'}])
    assert json.loads((tmp_path / 'h.json').read_text(encoding='utf-8'))
