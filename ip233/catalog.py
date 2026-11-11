"""Public model contracts. Snapshot is for menus; submissions use live metadata."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .client import Client, IP233Error

SNAPSHOT = Path(__file__).with_name("catalog.snapshot.json")


def normalize_catalog(payload):
    records = []
    for model in payload.get("data", []):
        if not isinstance(model, dict) or not model.get("model_name"):
            continue
        kind = "video" if model.get("video_ui_params") else "image" if model.get("image_ui_params") else None
        if not kind:
            continue
        doc = model.get("api_doc") or model.get("apiDoc") or {}
        if isinstance(doc, str):
            try:
                doc = json.loads(doc)
            except ValueError:
                doc = {}
        if not isinstance(doc, dict):
            doc = {}
        ui = model.get(kind + "_ui_params", {})
        limits = model.get("reference_limits") or ui.get("referenceLimits") or {}
        params = list(doc.get("params", []))
        known = {p.get("name") for p in params if isinstance(p, dict)}
        # The public image UI sometimes advertises a newer field than api_doc.
        aliases = {"background": "background", "output_format": "output_format",
                   "frame_count": "frame_count", "frame_duration_ms": "frame_duration_ms"}
        if kind == "image":
            for ui_key, api_key in aliases.items():
                entry = ui.get("params", {}).get(ui_key, {})
                if entry.get("enabled") and api_key not in known:
                    spec = {"name": api_key, "type": entry.get("type", "string"), "required": False}
                    choices = [x["value"] for x in entry.get("options", []) if isinstance(x, dict) and "value" in x]
                    if choices:
                        spec["enum"] = choices
                    for key in ("min", "max"):
                        if key in entry:
                            spec[key] = entry[key]
                    params.append(spec)
        records.append({
            "id": model["model_name"], "kind": kind,
            "params": params,
            "defaults": doc.get("basic_request_json") or doc.get("request_json") or {},
            "endpoints": doc.get("endpoints", []),
            "limits": limits, "ui_params": ui.get("params", {}),
            "contract_version": (model.get("ip233_contract") or {}).get("version", ""),
            "dispatch_mode": doc.get("dispatch_mode", ""),
        })
    if not records:
        raise IP233Error("Public model catalog was empty or invalid.")
    return records


def snapshot():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))["models"]


def model_names(kind):
    return [m["id"] for m in snapshot() if m["kind"] == kind and m["endpoints"]]


def live_catalog(config):
    with Client(config) as client:
        return normalize_catalog(client.request("GET", config.catalog_url))


def live_model(config, model, kind):
    for record in live_catalog(config):
        if record["id"] == model and record["kind"] == kind:
            if not record["endpoints"] or not record["params"]:
                raise IP233Error("This model has no published structured API contract. Choose a documented model or ask IP233 to publish its parameters.")
            return record
    raise IP233Error(f"Model {model!r} is not in the current {kind} catalog. Refresh the model list.")


def endpoint(record, mode):
    preferred = "/videos" if record["kind"] == "video" else "/images/edits" if mode == "edit" else "/images/generations"
    for entry in record["endpoints"]:
        path = entry.get("path", "").replace("{{base}}", "")
        if path.startswith("/v1/"):
            path = path[3:]
        if entry.get("method", "").upper() == "POST" and path == preferred:
            return path
    raise IP233Error("The selected model does not publish this generation/edit endpoint.")


def parse_parameters(text):
    try:
        def invalid_constant(value):
            raise ValueError(value)
        value = json.loads(text or "{}", parse_constant=invalid_constant)
    except ValueError:
        raise IP233Error("parameters_json must be a valid JSON object.") from None
    if not isinstance(value, dict):
        raise IP233Error("parameters_json must be a JSON object, not a list.")
    if {"model", "prompt", "charge_mode", "api_key"} & value.keys():
        raise IP233Error("Do not override model, prompt, charge_mode, or API keys in parameters_json.")
    return value


def validate_value(name, value, spec):
    kind = spec.get("type", "")
    if kind in ("int", "integer") and (not isinstance(value, int) or isinstance(value, bool)):
        raise IP233Error(f"{name} must be an integer.")
    if kind == "boolean" and not isinstance(value, bool):
        raise IP233Error(f"{name} must be a boolean.")
    if kind == "string" and not isinstance(value, str):
        raise IP233Error(f"{name} must be a string.")
    if kind.startswith("array") and not isinstance(value, list):
        raise IP233Error(f"{name} must be a JSON array.")
    choices = spec.get("enum")
    if choices and value not in choices:
        raise IP233Error(f"{name} must be one of {choices}.")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        lower, upper = spec.get("min"), spec.get("max")
        if lower is None and upper is None:
            match = re.fullmatch(r"(\d+)-(\d+)", str(spec.get("range", "")))
            if match:
                lower, upper = map(int, match.groups())
        if lower is not None and value < lower or upper is not None and value > upper:
            raise IP233Error(f"{name} is outside the published range {lower}..{upper}.")


def build_payload(record, prompt, parameters, references=None, mode="generate", allow_local_references=False):
    if not prompt.strip():
        raise IP233Error("Prompt must not be empty.")
    specs = {p["name"]: p for p in record["params"] if isinstance(p, dict) and "name" in p}
    # Start with request defaults, excluding sample prompts and sample reference URLs.
    reference_keys = {"images", "image", "mask", "reference_image_urls", "reference_videos", "reference_audios", "references"}
    defaults = record.get("defaults", {})
    payload = {k: v for k, v in defaults.items() if k not in reference_keys | {"model", "prompt"}}
    for name, spec in specs.items():
        if name not in payload and "default" in spec and name not in reference_keys:
            payload[name] = spec["default"]
    payload.update(parameters)
    if references:
        ref_key = "reference_image_urls" if record["kind"] == "video" else "images"
        if ref_key in parameters:
            raise IP233Error(f"Use either the reference input or {ref_key} in parameters_json.")
        payload[ref_key] = references
    # Some published image contracts list reference fields only in endpoint documentation.
    allowed = set(specs) | set(defaults)
    if mode == "edit":
        allowed.add("images")
    unknown = set(payload) - allowed
    if unknown:
        raise IP233Error(f"Unpublished parameters for {record['id']}: {', '.join(sorted(unknown))}. Check Model Info.")
    payload.update(model=record["id"], prompt=prompt)
    if record.get("dispatch_mode") == "async" and record["kind"] == "image" and "async" in specs:
        payload["async"] = True
    for name, spec in specs.items():
        if spec.get("required") and name not in payload:
            raise IP233Error(f"Missing required parameter: {name}. Add it to parameters_json.")
        if name in payload:
            validate_value(name, payload[name], spec)
    # All currently published image routes charge once per image and accept one result.
    if record["kind"] == "image" and payload.get("n", 1) != 1:
        raise IP233Error("IP233 image requests currently require n=1.")
    limits = record.get("limits", {})
    counts = {}
    for key, category in [("images", "images"), ("reference_image_urls", "images"), ("reference_videos", "videos"), ("reference_audios", "audios")]:
        values = payload.get(key, [])
        if values:
            if not isinstance(values, list):
                raise IP233Error(f"{key} must be an array.")
            from .client import secure_url
            for url in values:
                if not isinstance(url, str):
                    raise IP233Error(f"{key} must contain HTTPS URL strings.")
                description = specs.get(key, {}).get("description", "")
                if key == "images" and url.startswith("data:image/png;base64,") and "data uri" in description.lower():
                    if len(url) > 45 * 1024 * 1024:
                        raise IP233Error("Reference image data URI is too large.")
                    import base64
                    try:
                        base64.b64decode(url.partition(",")[2], validate=True)
                    except ValueError:
                        raise IP233Error("Reference image contains invalid base64.") from None
                else:
                    secure_url(url)
            counts[category] = counts.get(category, 0) + len(values)
            maximum = limits.get(category)
            if maximum is not None and counts[category] > maximum:
                raise IP233Error(f"{category}: model permits at most {maximum} references.")
    if limits.get("total") is not None and sum(counts.values()) > limits["total"]:
        raise IP233Error(f"This model permits at most {limits['total']} references in total.")
    if payload.get("references") and any(payload.get(k) for k in reference_keys - {"references"}):
        raise IP233Error("Do not mix structured references with other reference fields.")
    if payload.get("references"):
        from .client import secure_url
        structured_counts = {}
        for entry in payload["references"]:
            if not isinstance(entry, dict) or entry.get("type") not in ("image", "video", "audio") or entry.get("role", "reference") != "reference":
                raise IP233Error("Structured references need type=image|video|audio, role=reference, and source=HTTPS URL.")
            source = entry.get("source")
            if not isinstance(source, str):
                raise IP233Error("Structured reference source must be an HTTPS URL.")
            secure_url(source)
            category = {"image": "images", "video": "videos", "audio": "audios"}[entry["type"]]
            structured_counts[category] = structured_counts.get(category, 0) + 1
            if limits.get(category) is not None and structured_counts[category] > limits[category]:
                raise IP233Error(f"{category}: model permits at most {limits[category]} references.")
        if limits.get("total") is not None and sum(structured_counts.values()) > limits["total"]:
            raise IP233Error("Structured references exceed the model total limit.")
    if payload.get("mask"):
        from .client import secure_url
        secure_url(payload["mask"])
        if limits.get("mask", 0) == 0:
            raise IP233Error("The selected model does not advertise mask editing.")
    if mode == "edit" and not payload.get("images") and not allow_local_references:
        raise IP233Error("Image edit requires reference images.")
    if mode != "edit" and record["kind"] == "image" and any(payload.get(k) for k in ("images", "mask")):
        raise IP233Error("Reference images require edit mode.")
    return payload
