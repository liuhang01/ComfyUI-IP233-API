import pytest

from ip233.catalog import build_payload, endpoint, normalize_catalog, parse_parameters, snapshot
from ip233.client import IP233Error

MODELS = {model["id"]: model for model in snapshot()}


@pytest.mark.parametrize("model", [m for m in MODELS.values() if m["endpoints"] and m["params"]], ids=lambda m: m["id"])
def test_published_defaults_validate(model):
    payload = build_payload(model, "A studio photograph", {})
    assert payload["model"] == model["id"]
    assert payload["prompt"] == "A studio photograph"
    assert not payload.get("images")
    assert not payload.get("reference_image_urls")


@pytest.mark.parametrize("value", ["[]", "null", "bad", '{"seconds":NaN}', '{"charge_mode":"second"}', '{"model":"other"}'])
def test_invalid_json_or_reserved_fields(value):
    with pytest.raises(IP233Error):
        parse_parameters(value)


def test_video_model_specific_limits():
    a1 = MODELS["seedance2.0-A1"]
    with pytest.raises(IP233Error, match="seconds"):
        build_payload(a1, "test", {"seconds": 4})
    with pytest.raises(IP233Error, match="resolution"):
        build_payload(a1, "test", {"resolution": "1080p"})
    with pytest.raises(IP233Error):
        build_payload(a1, "test", {}, ["https://example.com/ref.png"] * 10)
    with pytest.raises(IP233Error):
        build_payload(a1, "test", {"references": [{"type": "video", "source": "https://example.com/v.mp4"}]})


def test_minimax_uses_published_contract_not_outdated_ui_hints():
    model = MODELS["minimax-h3"]
    with pytest.raises(IP233Error, match="resolution"):
        build_payload(model, "test", {"resolution": "720p"})
    assert build_payload(model, "test", {})["resolution"] == "768p"
    with pytest.raises(IP233Error, match="total"):
        build_payload(model, "test", {"reference_image_urls": ["https://a.com/i"] * 9,
                                      "reference_videos": ["https://a.com/v"] * 3,
                                      "reference_audios": ["https://a.com/a"]})


def test_edit_and_single_image_constraints():
    model = MODELS["gpt-image-2.6"]
    with pytest.raises(IP233Error):
        build_payload(model, "test", {"n": 2})
    with pytest.raises(IP233Error, match="quality"):
        build_payload(model, "test", {"quality": "high"})
    with pytest.raises(IP233Error):
        build_payload(model, "test", {}, [], "edit")
    assert build_payload(model, "test", {}, ["https://example.com/a.png"], "edit")["images"]
    assert endpoint(model, "edit") == "/images/edits"


def test_never_accept_insecure_reference_or_unknown_field():
    with pytest.raises(IP233Error):
        build_payload(MODELS["gpt-image-2.6"], "test", {}, ["http://example.com/ref.png"], "edit")
    with pytest.raises(IP233Error):
        build_payload(MODELS["seedance2.0-A1"], "test", {"made_up_parameter": True})
