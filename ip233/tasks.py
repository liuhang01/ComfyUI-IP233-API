"""Submit once, persist the task handle, and query without creating new jobs."""
from __future__ import annotations

import copy
import base64
import datetime
import json
import logging
import os
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from .catalog import build_payload, endpoint, live_model
from .client import Client, IP233Error, check_interrupt, interruptible_sleep

LOG = logging.getLogger(__name__)
KINDS = {"image": "/images/generations", "edit": "/images/edits", "video": "/videos"}
SUCCESS = {"completed", "complete", "succeeded", "success", "done", "finished"}
FAILURE = {"failed", "error", "cancelled", "canceled", "rejected", "expired"}


def output_directory():
    import folder_paths
    directory = Path(folder_paths.get_output_directory()) / "ip233"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def inner_response(response):
    data = response.get("data")
    return data if isinstance(data, dict) else response


def task_id(response):
    for value in (response, inner_response(response)):
        for key in ("task_id", "id", "taskId"):
            if isinstance(value.get(key), (str, int)) and value[key]:
                return str(value[key])
    return ""


def status(response):
    for value in (response, inner_response(response)):
        for key in ("status", "task_status", "state"):
            if isinstance(value.get(key), str):
                return value[key].lower()
    return "completed" if has_result(response) else "unknown"


def has_result(response):
    for value in (response, inner_response(response)):
        if any(value.get(key) for key in ("result_url", "video_url", "download_url", "output_url", "b64_json")):
            return True
        if value is not response and value.get("url"):
            return True
        for key in ("data", "output", "images"):
            items = value.get(key)
            if isinstance(items, list) and any(
                isinstance(item, dict) and any(item.get(k) for k in ("url", "b64_json", "video_url")) for item in items
            ):
                return True
    return False


def _write_journal(task):
    directory = output_directory() / "tasks"
    directory.mkdir(parents=True, exist_ok=True)
    identity = task.get("journal_id") or uuid.uuid4().hex
    if len(identity) != 32 or any(c not in "0123456789abcdef" for c in identity):
        raise IP233Error("Invalid local journal identity.")
    task["journal_id"] = identity
    destination = directory / (identity + ".json")
    temporary = directory / (identity + ".tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(task, handle, ensure_ascii=False, indent=2)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return str(destination)


def submit(config, kind, model, prompt, parameters, references=None, operation_key="", local_images=None):
    if kind not in KINDS:
        raise IP233Error("Unknown task kind.")
    record = live_model(config, model, "video" if kind == "video" else "image")
    mode = "edit" if kind == "edit" else "generate"
    multipart = None
    if local_images is not None:
        if kind != "edit":
            raise IP233Error("Local reference images require edit mode.")
        if references or parameters.get("images"):
            raise IP233Error("Choose local reference_images or hosted reference_urls, not both.")
        from .media import image_batch_png
        pngs = image_batch_png(local_images)
        maximum = record.get("limits", {}).get("images", 9)
        if len(pngs) > maximum or sum(map(len, pngs)) > 64 * 1024 * 1024:
            raise IP233Error(f"Local references exceed {maximum} images or 64 MiB in total.")
        description = " ".join(p.get("description", "") for p in record["params"] if p.get("name") == "images")
        if "multipart" in description.lower():
            multipart = [("image", (f"reference_{i + 1}.png", png, "image/png")) for i, png in enumerate(pngs)]
        elif "data uri" in description.lower():
            references = ["data:image/png;base64," + base64.b64encode(png).decode() for png in pngs]
        else:
            raise IP233Error("This model publishes URL-only references. Use hosted HTTPS reference_urls or an upload node returning public URLs.")
    payload = build_payload(record, prompt, parameters, references, mode, allow_local_references=bool(multipart))
    create_path = endpoint(record, mode)
    if operation_key and (len(operation_key) > 128 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for c in operation_key)):
        raise IP233Error("Operation key must use 1-128 ASCII letters, numbers, dash, underscore, or dot.")
    operation_key = operation_key.strip() or str(uuid.uuid4())
    task = {"kind": kind, "model": model, "id": "", "operation_key": operation_key,
            "base_url": config.base_url, "creation_path": create_path, "response": {},
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    journal_path = _write_journal(task)
    headers = {"Idempotency-Key": operation_key} if kind == "video" else {}
    if record.get("contract_version"):
        headers["X-IP233-Contract-Version"] = record["contract_version"]
    LOG.info("IP233 submitting %s; local task journal: %s", kind, journal_path)
    try:
        with Client(config) as client:
            if multipart:
                form = {key: json.dumps(value) if isinstance(value, (bool, list, dict)) else str(value) for key, value in payload.items()}
                response = client.request("POST", create_path, files=multipart, data=form, headers=headers)
            else:
                response = client.request("POST", create_path, json=payload, headers=headers)
    except IP233Error as exc:
        task["submission_status"] = "unconfirmed"
        _write_journal(task)
        raise IP233Error(f"{exc} Local journal: {journal_path}; operation key: {operation_key}") from None
    task.update(id=task_id(response), response=response, submission_status="received")
    _write_journal(task)
    if not task["id"] and not has_result(response):
        operation_id = response.get("operation_id") or inner_response(response).get("operation_id")
        hint = f" Operation ID: {operation_id}." if operation_id else ""
        raise IP233Error(f"Server returned no task ID or media.{hint} Check task history before resubmitting. Journal: {journal_path}")
    LOG.info("IP233 %s task id=%s; journal=%s", kind, task["id"] or "synchronous", journal_path)
    return task


def resume_task(config, kind, identity):
    if kind not in KINDS or not identity.strip():
        raise IP233Error("Provide a task ID and the original task kind.")
    return {"kind": kind, "id": identity.strip(), "model": "",
            "base_url": config.base_url, "creation_path": KINDS[kind], "response": {}}


def query(config, task):
    if task.get("base_url") != config.base_url:
        raise IP233Error("Task belongs to another API base URL. Use the configuration that created it.")
    if status(task.get("response", {})) in SUCCESS and has_result(task["response"]):
        return task
    if not task.get("id"):
        raise IP233Error("Task has no ID. Check the local journal and site task history.")
    if task.get("kind") not in KINDS:
        raise IP233Error("Invalid task kind.")
    with Client(config) as client:
        response = client.request("GET", KINDS[task["kind"]] + "/" + quote(str(task["id"]), safe=""))
    updated = copy.deepcopy(task)
    updated["response"] = response
    _write_journal(updated)
    return updated


def wait(config, task, poll_interval=5, max_wait=1800):
    if task.get("base_url") != config.base_url:
        raise IP233Error("Task belongs to another API base URL. Use the configuration that created it.")
    if poll_interval < 1 or max_wait < 1:
        raise IP233Error("Poll interval and wait timeout must be positive.")
    deadline = time.monotonic() + max_wait
    current = task
    while True:
        check_interrupt()
        state = status(current.get("response", {}))
        if state in FAILURE:
            response = inner_response(current["response"])
            error = response.get("error") or response.get("message") or state
            if isinstance(error, dict):
                error = error.get("message", state)
            detail = str(error).replace(config.api_key, "[REDACTED]")
            raise IP233Error(f"IP233 task {current.get('id')} failed: {detail[:700]}")
        if state in SUCCESS:
            return current
        if time.monotonic() >= deadline:
            raise IP233Error(f"Wait timed out for task {current.get('id')}. Use Resume Task to continue querying this ID; do not submit again.")
        # GET failures do not cause a new submission. User can resume after network/auth fixes.
        current = query(config, current)
        if status(current.get("response", {})) not in SUCCESS | FAILURE:
            interruptible_sleep(min(poll_interval, max(0, deadline - time.monotonic())))
