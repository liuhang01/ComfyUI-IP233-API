import io
import json
from unittest.mock import Mock

import pytest
import requests

from ip233.client import Client, IP233Error, ServiceConfig, make_config


def response(status=200, body=None, headers=None):
    value = requests.Response()
    value.status_code = status
    value.headers.update(headers or {})
    value.raw = io.BytesIO(body if isinstance(body, bytes) else json.dumps(body or {}).encode())
    return value


def test_api_auth_and_catalog_without_auth():
    config = ServiceConfig("test-secret")
    with Client(config) as client:
        client.session.request = Mock(side_effect=[response(body={"ok": True}), response(body={"ok": True})])
        client.request("GET", "/models")
        client.request("GET", config.catalog_url)
        calls = client.session.request.call_args_list
        assert calls[0].kwargs["headers"]["Authorization"] == "Bearer test-secret"
        assert "Authorization" not in calls[1].kwargs["headers"]
        assert calls[0].kwargs["allow_redirects"] is False
        assert calls[0].kwargs["stream"] is True
        assert client.session.verify is True


def test_redirect_does_not_leak_key_and_download_is_atomic(tmp_path):
    seen = []
    queue = [response(302, headers={"Location": "https://cdn.example.org/result.mp4"}),
             response(body=b"media-data")]
    with Client(ServiceConfig("test-secret")) as client:
        def send(method, url, **kwargs):
            seen.append((url, dict(kwargs["headers"])))
            return queue.pop(0)
        client.session.request = send
        target = tmp_path / "result.mp4"
        client.download("https://api-new.ip233.com/v1/videos/id/content", target)
    assert target.read_bytes() == b"media-data"
    assert seen[0][1]["Authorization"] == "Bearer test-secret"
    assert "Authorization" not in seen[1][1]
    assert not target.with_name("result.mp4.part").exists()


def test_post_is_never_retried():
    with Client(ServiceConfig("secret")) as client:
        client.session.request = Mock(side_effect=requests.Timeout("secret"))
        with pytest.raises(IP233Error, match="may have accepted") as exc:
            client.request("POST", "/videos", json={"prompt": "test"})
        assert client.session.request.call_count == 1
        assert "secret" not in str(exc.value)


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_http_errors_fail_without_retry_and_redact(status):
    with Client(ServiceConfig("test-secret")) as client:
        client.session.request = Mock(return_value=response(status, {"error": {"message": "bad test-secret"}}))
        with pytest.raises(IP233Error) as exc:
            client.request("GET", "/videos/id")
        assert str(status) in str(exc.value)
        assert "test-secret" not in str(exc.value)
        assert client.session.request.call_count == 1


def test_oversized_download_leaves_no_partial(tmp_path):
    target = tmp_path / "big.mp4"
    with Client(ServiceConfig("secret")) as client:
        client.session.request = Mock(return_value=response(body=b"12345678"))
        with pytest.raises(IP233Error):
            client.download("https://example.org/big.mp4", target, max_bytes=4)
    assert list(tmp_path.iterdir()) == []


def test_config_environment_and_repr(monkeypatch):
    monkeypatch.setenv("IP233_API_KEY", "environment-secret")
    config = make_config(base_url="https://api-new.ip233.com")
    assert config.base_url.endswith("/v1")
    assert config.api_key == "environment-secret"
    assert "environment-secret" not in repr(config)
    with pytest.raises(IP233Error):
        ServiceConfig("key", "http://example.com/v1")
    with pytest.raises(IP233Error):
        ServiceConfig("key", "https://user:password@example.com/v1")


def test_failed_task_response_keeps_id_for_task_layer():
    payload = {"id": "original-task", "status": "failed", "error": {"message": "rejected"}}
    with Client(ServiceConfig("key")) as client:
        client.session.request = Mock(return_value=response(body=payload))
        assert client.request("GET", "/videos/original-task") == payload
