import base64
import hashlib
import json
from unittest.mock import Mock

import pytest

from tools.submit_manager import append_entry, read_catalog_text


def git_blob_payload(content):
    sha = hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()
    return {"sha": sha, "size": len(content), "encoding": "base64",
            "content": base64.encodebytes(content).decode("ascii")}


def test_small_catalog_uses_inline_base64_without_blob_request():
    content = b'{"custom_nodes": [{"title": "existing"}]}\n'
    fetch_blob = Mock()
    assert read_catalog_text(git_blob_payload(content), fetch_blob) == content.decode()
    fetch_blob.assert_not_called()


def test_large_catalog_reads_exact_blob_when_contents_api_omits_content():
    content = b'{"custom_nodes": [{"description": "' + b"x" * (1024 * 1024) + b'"}]}\n'
    blob = git_blob_payload(content)
    metadata = {"sha": blob["sha"], "size": blob["size"], "encoding": "none", "content": ""}
    fetch_blob = Mock(return_value=blob)
    assert read_catalog_text(metadata, fetch_blob) == content.decode()
    fetch_blob.assert_called_once_with(blob["sha"])


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("content", "not-base64!", "invalid Base64"),
        ("size", 999, "decoded size"),
        ("sha", "0" * 40, "Git blob SHA"),
        ("encoding", "utf-8", "Base64 content"),
    ],
)
def test_catalog_invalid_inline_content_fails_clearly(field, value, message):
    payload = git_blob_payload(b'{"custom_nodes": []}\n')
    payload[field] = value
    with pytest.raises(RuntimeError, match=message):
        read_catalog_text(payload, Mock())


@pytest.mark.parametrize("field,value,message", [
    ("sha", "0" * 40, "blob SHA"),
    ("size", 12345, "blob size"),
])
def test_fetched_blob_must_match_contents_metadata(field, value, message):
    blob = git_blob_payload(b'{"custom_nodes": []}\n')
    metadata = {"sha": blob["sha"], "size": blob["size"], "encoding": "none", "content": ""}
    blob[field] = value
    with pytest.raises(RuntimeError, match=message):
        read_catalog_text(metadata, Mock(return_value=blob))


def test_catalog_requires_valid_metadata_before_requesting_blob():
    fetch_blob = Mock()
    with pytest.raises(RuntimeError, match="valid blob SHA"):
        read_catalog_text({"sha": "../invalid", "size": 10, "encoding": "none", "content": ""}, fetch_blob)
    fetch_blob.assert_not_called()


def test_catalog_rejects_invalid_utf8_after_integrity_validation():
    with pytest.raises(RuntimeError, match="UTF-8"):
        read_catalog_text(git_blob_payload(b"\xff"), Mock())


def test_manager_submission_preserves_existing_text_exactly():
    source = '{\n    "custom_nodes": [\n        {"title": "existing", "note": "\\u4e2d"}  \n    ]\n}\n'
    result = append_entry(source, {"title": "IP233", "id": "ip233-ai-nodes"})
    assert json.loads(result)["custom_nodes"][0] == json.loads(source)["custom_nodes"][0]
    assert '"note": "\\u4e2d"' in result
    prefix, suffix = source.split('  \n    ]')
    assert result.startswith(prefix + ",\n")
    assert result.endswith('  \n    ]' + suffix)


def test_install_archive_excludes_local_keys_and_caches(monkeypatch, tmp_path):
    from zipfile import ZipFile
    from tools import package_release
    monkeypatch.setattr(package_release, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="1.2.3"\n')
    (tmp_path / "__init__.py").write_text('# node entrypoint\n')
    (tmp_path / "ip233.local.json").write_text('{"api_key":"test-do-not-ship"}')
    (tmp_path / ".env").write_text('IP233_API_KEY=test-do-not-ship')
    cached = tmp_path / "ip233" / "__pycache__"
    cached.mkdir(parents=True)
    (cached / "module.pyc").write_bytes(b'cache')
    publication = tmp_path / ".github" / "workflows"
    publication.mkdir(parents=True)
    (publication / "import-source.yml").write_text('name: Temporary source import\n')
    package_release.main()
    with ZipFile(tmp_path / "dist" / "ComfyUI-IP233-API-1.2.3.zip") as archive:
        names = archive.namelist()
        assert 'ComfyUI-IP233-API/__init__.py' in names
        assert not any('local.json' in name or '__pycache__' in name or name.endswith('/.env') for name in names)
        assert not any(name.endswith('/import-source.yml') for name in names)


def test_manager_only_preparation_does_not_invent_registry_publisher(monkeypatch, tmp_path):
    import sys
    from unittest.mock import Mock
    import tomlkit
    from tools import prepare_release
    monkeypatch.setattr(prepare_release, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="0.1.0"\n[project.urls]\n[tool.comfy]\nDisplayName="IP233"\n')
    monkeypatch.setattr(sys, "argv", ["prepare_release.py", "--repository", "https://github.com/example-owner/ComfyUI-IP233-API"])
    response = Mock()
    response.json.return_value = {"private": False, "archived": False}
    monkeypatch.setattr(prepare_release.requests, "get", Mock(return_value=response))
    prepare_release.main()
    document = tomlkit.loads((tmp_path / "pyproject.toml").read_text())
    assert "PublisherId" not in document["tool"]["comfy"]
    assert document["project"]["urls"]["Repository"].endswith("ComfyUI-IP233-API")
    entry = json.loads((tmp_path / ".release" / "manager-entry.json").read_text())
    assert entry["author"] == "example-owner"
