import json
from unittest.mock import Mock

import pytest

from ip233 import tasks
from ip233.catalog import snapshot
from ip233.client import IP233Error, ServiceConfig


@pytest.fixture
def output(monkeypatch, tmp_path):
    monkeypatch.setattr(tasks, "output_directory", lambda: tmp_path)
    return tmp_path


def test_submit_once_and_persist_without_api_key(monkeypatch, output):
    model = next(m for m in snapshot() if m["id"] == "seedance2.0-A1")
    monkeypatch.setattr(tasks, "live_model", lambda *args: model)
    request = Mock(return_value={"id": "task-1", "status": "queued"})
    monkeypatch.setattr(tasks.Client, "request", request)
    task = tasks.submit(ServiceConfig("secret-never-save"), "video", model["id"], "test", {})
    assert request.call_count == 1
    assert request.call_args.args[:2] == ("POST", "/videos")
    assert request.call_args.kwargs["headers"]["Idempotency-Key"] == task["operation_key"]
    assert request.call_args.kwargs["headers"]["X-IP233-Contract-Version"] == model["contract_version"]
    saved = list((output / "tasks").glob("*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text())["id"] == "task-1"
    assert "secret-never-save" not in saved[0].read_text()


def test_wait_only_queries_original_task(monkeypatch, output):
    config = ServiceConfig("secret")
    task = tasks.resume_task(config, "video", "original/id")
    request = Mock(side_effect=[{"status": "running"}, {"status": "completed", "result_url": "https://cdn.example.com/result.mp4"}])
    monkeypatch.setattr(tasks.Client, "request", request)
    monkeypatch.setattr(tasks, "interruptible_sleep", lambda _: None)
    complete = tasks.wait(config, task, max_wait=5)
    assert complete["id"] == "original/id"
    assert all(c.args == ("GET", "/videos/original%2Fid") for c in request.call_args_list)


def test_failed_task_contains_id_without_new_submission(output):
    config = ServiceConfig("secret")
    task = tasks.resume_task(config, "video", "failed-1")
    task["response"] = {"status": "failed", "error": {"message": "rejected secret"}}
    with pytest.raises(IP233Error, match="failed-1") as exc:
        tasks.wait(config, task)
    assert "secret" not in str(exc.value)


def test_resume_requires_original_base_url(output):
    task = tasks.resume_task(ServiceConfig("key"), "image", "task-1")
    with pytest.raises(IP233Error, match="another API"):
        tasks.query(ServiceConfig("other", "https://other.example.com/v1"), task)


def test_local_gpt_image_edit_uses_documented_multipart(monkeypatch, output):
    import torch
    model = next(m for m in snapshot() if m["id"] == "gpt-image-2.6")
    monkeypatch.setattr(tasks, "live_model", lambda *args: model)
    request = Mock(return_value={"task_id": "image-edit-1", "status": "queued"})
    monkeypatch.setattr(tasks.Client, "request", request)
    tasks.submit(ServiceConfig("secret"), "edit", model["id"], "test", {}, local_images=torch.zeros((2, 2, 2, 3)))
    assert request.call_args.args == ("POST", "/images/edits")
    assert "json" not in request.call_args.kwargs
    assert len(request.call_args.kwargs["files"]) == 2
    assert request.call_args.kwargs["data"]["model"] == model["id"]


def test_local_gemini_edit_uses_valid_image_data_uri(monkeypatch, output):
    import base64
    import io
    from PIL import Image
    import torch
    model = next(m for m in snapshot() if m["id"] == "gemini-3.1-flash-image-preview")
    monkeypatch.setattr(tasks, "live_model", lambda *args: model)
    request = Mock(return_value={"task_id": "edit-gemini", "status": "queued"})
    monkeypatch.setattr(tasks.Client, "request", request)
    tasks.submit(ServiceConfig("secret"), "edit", model["id"], "test", {}, local_images=torch.zeros((1, 2, 2, 3)))
    value = request.call_args.kwargs["json"]["images"][0]
    header, content = value.split(",", 1)
    assert header == "data:" + "image/png;base64"
    assert Image.open(io.BytesIO(base64.b64decode(content))).size == (2, 2)


def test_local_image_rejected_for_url_only_contract(monkeypatch, output):
    import torch
    model = next(m for m in snapshot() if m["id"] == "gpt-image-2")
    monkeypatch.setattr(tasks, "live_model", lambda *args: model)
    request = Mock()
    monkeypatch.setattr(tasks.Client, "request", request)
    with pytest.raises(IP233Error, match="URL-only"):
        tasks.submit(ServiceConfig("secret"), "edit", model["id"], "test", {}, local_images=torch.zeros((1, 2, 2, 3)))
    request.assert_not_called()


def test_completed_task_still_requires_original_configuration():
    task = tasks.resume_task(ServiceConfig("key"), "video", "finished")
    task["response"] = {"status": "completed", "result_url": "https://cdn.example.org/video.mp4"}
    with pytest.raises(IP233Error, match="another API"):
        tasks.wait(ServiceConfig("key", "https://other.example.com/v1"), task)
