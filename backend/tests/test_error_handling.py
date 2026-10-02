"""An unhandled exception must reach the browser as a readable JSON 500.

Starlette's ServerErrorMiddleware sits outside CORSMiddleware, so without
JsonErrorMiddleware this response arrives with no Access-Control-Allow-Origin
and the frontend reports the API as offline.
"""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.middleware import CORS_ALLOW_ORIGINS

SECRET = "secret-token SELECT * FROM users"


@pytest.fixture()
def throwaway_routes():
    """Register routes that fail in interesting ways, then remove them."""

    @app.get("/__test__/unhandled")
    def _unhandled():
        raise RuntimeError(SECRET)

    @app.get("/__test__/http-exception")
    def _http_exception():
        raise HTTPException(status_code=404, detail="Strategy gone not found")

    @app.get("/__test__/validation")
    def _validation(cash: int):
        return {"cash": cash}

    yield

    app.router.routes[:] = [
        r for r in app.router.routes if not getattr(r, "path", "").startswith("/__test__/")
    ]


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_error_is_json_500_with_cors_header(throwaway_routes, client):
    origin = CORS_ALLOW_ORIGINS[0]
    resp = client.get("/__test__/unhandled", headers={"Origin": origin})

    assert resp.status_code == 500
    assert resp.headers["access-control-allow-origin"] == origin
    assert resp.json() == {"detail": "Internal server error"}
    assert SECRET not in resp.text


def test_unhandled_error_has_no_cors_header_for_other_origin(throwaway_routes, client):
    resp = client.get("/__test__/unhandled", headers={"Origin": "http://evil.example"})

    assert resp.status_code == 500
    assert "access-control-allow-origin" not in resp.headers


def test_http_exception_is_not_swallowed(throwaway_routes, client):
    origin = CORS_ALLOW_ORIGINS[1]
    resp = client.get("/__test__/http-exception", headers={"Origin": origin})

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Strategy gone not found"}
    assert resp.headers["access-control-allow-origin"] == origin


def test_validation_errors_are_not_swallowed(throwaway_routes, client):
    resp = client.get("/__test__/validation", params={"cash": "not-an-int"})

    assert resp.status_code == 422
    assert isinstance(resp.json()["detail"], list)