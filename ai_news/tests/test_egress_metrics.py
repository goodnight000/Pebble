import os
import sys
import types
import unittest

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres")

sys.path.insert(0, os.path.abspath("ai_news"))

if "supabase" not in sys.modules:
    supabase_stub = types.ModuleType("supabase")
    supabase_stub.create_client = lambda *args, **kwargs: None
    supabase_stub.__path__ = []
    supabase_lib_stub = types.ModuleType("supabase.lib")
    supabase_lib_stub.__path__ = []
    supabase_client_options_stub = types.ModuleType("supabase.lib.client_options")

    class ClientOptions:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    supabase_client_options_stub.ClientOptions = ClientOptions
    sys.modules["supabase"] = supabase_stub
    sys.modules["supabase.lib"] = supabase_lib_stub
    sys.modules["supabase.lib.client_options"] = supabase_client_options_stub

from app.llm.cache import delete_by_prefix, get_cached, set_cached


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read_source(relative_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, relative_path), "r", encoding="utf-8") as handle:
        return handle.read()


class EgressMetricsMiddlewareTests(unittest.TestCase):
    def setUp(self):
        delete_by_prefix("")

    def tearDown(self):
        delete_by_prefix("")

    def test_json_responses_record_response_bytes(self):
        from app.observability.egress import (
            EgressMetricsMiddleware,
            get_egress_metrics_store,
            reset_egress_metrics_store,
        )

        reset_egress_metrics_store()
        app = FastAPI()
        app.add_middleware(EgressMetricsMiddleware)

        @app.get("/bytes")
        def bytes_route():
            return JSONResponse({"ok": True, "items": [1, 2, 3]})

        client = TestClient(app)
        response = client.get("/bytes", headers={"user-agent": "pytest-egress"})

        self.assertEqual(response.status_code, 200)
        snapshot = get_egress_metrics_store().snapshot(limit=5)
        self.assertEqual(snapshot["summary"]["total_requests"], 1)
        self.assertGreater(snapshot["summary"]["total_response_bytes"], 0)
        self.assertEqual(snapshot["top_paths"][0]["path"], "/bytes")
        self.assertEqual(snapshot["top_paths"][0]["user_agent"], "pytest-egress")

    def test_streaming_responses_count_chunk_bytes(self):
        from app.observability.egress import (
            EgressMetricsMiddleware,
            get_egress_metrics_store,
            reset_egress_metrics_store,
        )

        reset_egress_metrics_store()
        app = FastAPI()
        app.add_middleware(EgressMetricsMiddleware)

        @app.get("/stream-bytes")
        def stream_route():
            return StreamingResponse(iter([b"ab", b"cdef"]), media_type="text/plain")

        client = TestClient(app)
        response = client.get("/stream-bytes")

        self.assertEqual(response.status_code, 200)
        snapshot = get_egress_metrics_store().snapshot(limit=5)
        self.assertEqual(snapshot["top_paths"][0]["path"], "/stream-bytes")
        self.assertEqual(snapshot["top_paths"][0]["response_bytes"], 6)

    def test_cache_helpers_record_hits_misses_and_sets(self):
        from app.observability.egress import (
            EgressMetricsMiddleware,
            get_egress_metrics_store,
            reset_egress_metrics_store,
        )

        reset_egress_metrics_store()
        app = FastAPI()
        app.add_middleware(EgressMetricsMiddleware)

        @app.get("/cache")
        def cache_route():
            before = get_cached("egress:test:key")
            set_cached("egress:test:key", {"cached": True}, ttl=60)
            after = get_cached("egress:test:key")
            return {"before": before, "after": after}

        client = TestClient(app)
        response = client.get("/cache")

        self.assertEqual(response.status_code, 200)
        snapshot = get_egress_metrics_store().snapshot(limit=5)
        self.assertEqual(snapshot["top_paths"][0]["cache_hits"], 1)
        self.assertEqual(snapshot["top_paths"][0]["cache_misses"], 1)
        self.assertEqual(snapshot["top_paths"][0]["cache_sets"], 1)

    def test_dependency_bytes_are_attached_to_request_record(self):
        from app.observability.egress import (
            EgressMetricsMiddleware,
            get_egress_metrics_store,
            note_dependency_egress,
            reset_egress_metrics_store,
        )

        reset_egress_metrics_store()
        app = FastAPI()
        app.add_middleware(EgressMetricsMiddleware)

        @app.get("/dependency")
        def dependency_route():
            note_dependency_egress(service="supabase_storage", bytes_count=4096, target="digests/today.json")
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/dependency")

        self.assertEqual(response.status_code, 200)
        snapshot = get_egress_metrics_store().snapshot(limit=5)
        self.assertEqual(snapshot["summary"]["total_dependency_bytes"], 4096)
        self.assertEqual(snapshot["top_paths"][0]["dependency_bytes"], 4096)
        self.assertEqual(snapshot["top_paths"][0]["dependency_services"]["supabase_storage"], 4096)
        self.assertEqual(snapshot["top_dependency_targets"][0]["service"], "supabase_storage")
        self.assertEqual(snapshot["top_dependency_targets"][0]["target"], "digests/today.json")
        self.assertEqual(snapshot["top_dependency_targets"][0]["bytes"], 4096)
        self.assertIn("cache_metrics_scope", snapshot["summary"])


class EgressMetricsWiringTests(unittest.TestCase):
    def test_main_registers_egress_metrics_middleware(self):
        main_source = _read_source("ai_news/app/api/main.py")
        self.assertIn("EgressMetricsMiddleware", main_source)
        self.assertIn("app.add_middleware(EgressMetricsMiddleware)", main_source)

    def test_admin_router_exposes_egress_snapshot_endpoint(self):
        admin_source = _read_source("ai_news/app/api/routes_admin.py")
        self.assertIn('@router.get("/egress")', admin_source)
        self.assertIn('@router.post("/egress/reset")', admin_source)
        self.assertIn("get_egress_metrics_store", admin_source)
        self.assertIn("x-egress-debug-token", admin_source)
        self.assertIn("EGRESS_DEBUG_TOKEN", _read_source("ai_news/app/config.py"))


if __name__ == "__main__":
    unittest.main()
