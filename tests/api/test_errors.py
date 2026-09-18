"""Tests for structured error handling."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.api.errors import APIError, register_exception_handlers


@pytest.fixture()
def error_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/fail")
    def fail() -> None:
        raise APIError(
            status_code=404,
            error_code="NOT_FOUND",
            message="Resource not found",
            detail={"resource_id": "42"},
        )

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("something broke")

    return app


@pytest.fixture()
def error_client(error_app: FastAPI) -> TestClient:
    return TestClient(error_app, raise_server_exceptions=False)


def test_api_error_structured_response(error_client: TestClient) -> None:
    response = error_client.get("/fail")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Resource not found"
    assert body["error"]["detail"] == {"resource_id": "42"}


def test_unhandled_error_hides_internals(error_client: TestClient) -> None:
    response = error_client.get("/crash")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "something broke" not in body["error"]["message"]


def test_api_error_without_detail() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/bare")
    def bare() -> None:
        raise APIError(status_code=400, error_code="BAD_REQUEST", message="Bad")

    client = TestClient(app)
    response = client.get("/bare")
    assert response.status_code == 400
    body = response.json()
    assert "detail" not in body["error"]
