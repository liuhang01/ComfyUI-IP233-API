import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_pack(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_comfy_discovery_is_portable_without_directory_name_assumptions(monkeypatch):
    import requests
    monkeypatch.setattr(requests.Session, "request", lambda *a, **k: pytest.fail("Import-time network request"))
    pack = load_pack("comfy_node_pack_different_install_name")
    assert len(pack.NODE_CLASS_MAPPINGS) == 12
    for key, cls in pack.NODE_CLASS_MAPPINGS.items():
        assert key.startswith("IP233")
        assert key in pack.NODE_DISPLAY_NAME_MAPPINGS
        assert cls.INPUT_TYPES().get("required")
        assert hasattr(cls, cls.FUNCTION)
        assert len(cls.RETURN_TYPES) == len(cls.RETURN_NAMES)


def test_example_workflows_have_consistent_links_and_no_api_keys():
    paths = list((ROOT / "examples" / "workflows").glob("*.json"))
    assert len(paths) == 4
    for path in paths:
        document = json.loads(path.read_text())
        nodes = {n["id"]: n for n in document["nodes"]}
        for identity, source, slot, target, target_slot, kind in document["links"]:
            assert identity in nodes[source]["outputs"][slot]["links"]
            assert nodes[target]["inputs"][target_slot]["link"] == identity
            assert nodes[target]["inputs"][target_slot]["type"] == kind
        for node in nodes.values():
            if node["type"] == "IP233Config":
                assert node["widgets_values"][-1] == ""
