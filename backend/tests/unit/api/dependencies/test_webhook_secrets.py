import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from relaymaid.api.dependencies.webhook_secrets import (
    WebhookSecretManagerDependency,
    get_webhook_secret_manager,
)
from relaymaid.security.webhook_secrets import WebhookSecretManager


@pytest.fixture
def manager() -> WebhookSecretManager:
    return WebhookSecretManager(Fernet.generate_key().decode())


def make_request(app: FastAPI) -> Request:
    return Request({"type": "http", "app": app})


def test_returns_initialized_manager_without_replacing_it(
    manager: WebhookSecretManager,
) -> None:
    app = FastAPI()
    app.state.webhook_secret_manager = manager
    for _ in range(2):
        assert get_webhook_secret_manager(make_request(app)) is manager
    assert app.state.webhook_secret_manager is manager


def test_rejects_missing_manager() -> None:
    app = FastAPI()
    with pytest.raises(
        RuntimeError, match=r"^Webhook secret manager is not initialized$"
    ):
        get_webhook_secret_manager(make_request(app))
    assert not hasattr(app.state, "webhook_secret_manager")


@pytest.mark.parametrize("invalid_manager", [None, "manager", {}, 123, object()])
def test_rejects_invalid_manager_in_app_state(invalid_manager: object) -> None:
    app = FastAPI()
    app.state.webhook_secret_manager = invalid_manager
    with pytest.raises(
        RuntimeError, match=r"^Webhook secret manager is not initialized$"
    ):
        get_webhook_secret_manager(make_request(app))
    assert app.state.webhook_secret_manager is invalid_manager


def test_manager_is_resolved_from_each_requests_app(
    manager: WebhookSecretManager,
) -> None:
    first, second = FastAPI(), FastAPI()
    other_manager = WebhookSecretManager(Fernet.generate_key().decode())
    first.state.webhook_secret_manager = manager
    second.state.webhook_secret_manager = other_manager
    assert get_webhook_secret_manager(make_request(first)) is manager
    assert get_webhook_secret_manager(make_request(second)) is other_manager


def test_dependency_annotation_injects_functional_manager(
    manager: WebhookSecretManager,
) -> None:
    app = FastAPI()
    app.state.webhook_secret_manager = manager

    @app.get("/test-secret")
    def use_manager(injected: WebhookSecretManagerDependency) -> dict[str, str]:
        assert injected is manager
        return {"encrypted": injected.encrypt("test-secret")}

    with TestClient(app) as client:
        response = client.get("/test-secret")
    assert response.status_code == 200
    assert manager.decrypt(response.json()["encrypted"]) == "test-secret"


@pytest.mark.parametrize("state", ["missing", "none", "wrong_type"])
def test_dependency_failure_prevents_route_execution(state: str) -> None:
    app = FastAPI()
    if state == "none":
        app.state.webhook_secret_manager = None
    elif state == "wrong_type":
        app.state.webhook_secret_manager = "invalid"
    route_called = False

    @app.get("/test-secret")
    def use_manager(injected: WebhookSecretManagerDependency) -> dict[str, str]:
        nonlocal route_called
        route_called = True
        return {"secret": injected.generate_secret()}

    with (
        TestClient(app) as client,
        pytest.raises(
            RuntimeError, match=r"^Webhook secret manager is not initialized$"
        ),
    ):
        client.get("/test-secret")
    assert route_called is False
