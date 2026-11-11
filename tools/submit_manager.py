"""Prepare or submit a focused ComfyUI-Manager registration pull request."""
import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "Comfy-Org/ComfyUI-Manager"


def read_catalog_text(source, fetch_blob):
    sha = source.get("sha")
    size = source.get("size")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("GitHub catalog metadata is missing a valid blob SHA.")
    if type(size) is not int or size < 0:
        raise RuntimeError("GitHub catalog metadata has an invalid file size.")
    # Contents API omits content above 1 MiB. Read that exact immutable blob.
    payload = source
    if source.get("encoding") == "none" or not source.get("content"):
        payload = fetch_blob(sha)
    if not isinstance(payload, dict) or payload.get("sha") != sha:
        raise RuntimeError("GitHub catalog blob SHA does not match the file metadata.")
    if payload.get("size") != size:
        raise RuntimeError("GitHub catalog blob size does not match the file metadata.")
    content = payload.get("content")
    if payload.get("encoding") != "base64" or not isinstance(content, str):
        raise RuntimeError("GitHub catalog blob did not return Base64 content.")
    try:
        encoded = re.sub(rb"[\t\n\r ]+", b"", content.encode("ascii"))
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise RuntimeError("GitHub catalog blob contains invalid Base64 content.") from exc
    if len(decoded) != size:
        raise RuntimeError("GitHub catalog decoded size does not match the file metadata.")
    git_blob = b"blob " + str(len(decoded)).encode("ascii") + b"\0" + decoded
    if hashlib.sha1(git_blob).hexdigest() != sha:
        raise RuntimeError("GitHub catalog content does not match its Git blob SHA.")
    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("GitHub catalog content is not valid UTF-8.") from exc


def append_entry(source, entry):
    catalog = json.loads(source)
    nodes = catalog.get("custom_nodes")
    if not isinstance(nodes, list) or not nodes:
        raise RuntimeError("Unexpected upstream catalog shape; refusing to rewrite it.")
    opening = re.search(r'"custom_nodes"\s*:\s*\[', source)
    if not opening:
        raise RuntimeError("Cannot locate the upstream custom_nodes array.")
    decoder = json.JSONDecoder()
    cursor, last_end = opening.end(), None
    for _ in nodes:
        while source[cursor].isspace():
            cursor += 1
        _, last_end = decoder.raw_decode(source, cursor)
        cursor = last_end
        while source[cursor].isspace():
            cursor += 1
        if source[cursor] == ",":
            cursor += 1
    if source[cursor] != "]":
        raise RuntimeError("Unexpected catalog boundary; refusing to rewrite it.")
    addition = "\n".join("        " + line for line in json.dumps(entry, ensure_ascii=False, indent=4).splitlines())
    updated = source[:last_end] + ",\n" + addition + source[last_end:]
    catalog["custom_nodes"].append(entry)
    if json.loads(updated) != catalog:
        raise RuntimeError("Manager catalog verification failed.")
    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit", action="store_true", help="Create a fork branch and actual upstream PR")
    args = parser.parse_args()
    path = ROOT / ".release" / "manager-entry.json"
    if not path.exists():
        parser.error("Run prepare_release.py with the real public repository and publisher first.")
    entry = json.loads(path.read_text(encoding="utf-8"))
    if not args.submit:
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        print("Dry run only. No fork, branch, commit, or PR was created.")
        return
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        parser.error("Set GITHUB_TOKEN locally with permission to create a fork, branch, and PR. Do not put the token in chat or commit it.")
    with requests.Session() as session:
        session.headers.update({"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                                "X-GitHub-Api-Version": "2022-11-28"})
        def api(method, endpoint, **kwargs):
            response = session.request(method, "https://api.github.com" + endpoint, timeout=45, **kwargs)
            if not response.ok:
                raise RuntimeError(f"GitHub HTTP {response.status_code}; no automatic write retry was made. Check existing branches and PRs before rerunning.")
            return response.json()
        owner = api("GET", "/user")["login"]
        upstream = api("GET", "/repos/" + UPSTREAM)
        default_branch = upstream["default_branch"]
        head_branch = "register-ip233-ai-nodes"
        pulls = api("GET", f"/repos/{UPSTREAM}/pulls", params={"head": owner + ":" + head_branch, "state": "open"})
        if pulls:
            print("Existing PR: " + pulls[0]["html_url"])
            return
        ref = api("GET", f"/repos/{UPSTREAM}/git/ref/heads/{default_branch}")
        base_sha = ref["object"]["sha"]
        source = api("GET", f"/repos/{UPSTREAM}/contents/custom-node-list.json", params={"ref": base_sha})
        original_text = read_catalog_text(
            source, lambda sha: api("GET", f"/repos/{UPSTREAM}/git/blobs/{sha}")
        )
        try:
            catalog = json.loads(original_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("The upstream Manager catalog is not valid JSON.") from exc
        nodes = catalog.get("custom_nodes") if isinstance(catalog, dict) else None
        if not isinstance(nodes, list):
            raise RuntimeError("Unexpected upstream Manager catalog shape.")
        if any(node.get("id") == entry["id"] or node.get("reference") == entry["reference"] for node in nodes):
            print("This package is already listed upstream; no PR is needed.")
            return
        updated_text = append_entry(original_text, entry)
        api("POST", f"/repos/{UPSTREAM}/forks")
        fork = f"{owner}/{upstream['name']}"
        ready = False
        for _ in range(12):
            response = session.get(f"https://api.github.com/repos/{fork}", timeout=30)
            if response.ok:
                ready = True
                break
            if response.status_code != 404:
                raise RuntimeError(f"GitHub HTTP {response.status_code} while waiting for fork.")
            time.sleep(2)
        if not ready:
            raise RuntimeError("Fork is still being prepared. Wait, inspect it, and rerun.")
        api("POST", f"/repos/{fork}/git/refs", json={"ref": "refs/heads/" + head_branch, "sha": base_sha})
        api("PUT", f"/repos/{fork}/contents/custom-node-list.json", json={
            "message": "Register IP233 Image and Video nodes", "branch": head_branch, "sha": source["sha"],
            "content": base64.b64encode(updated_text.encode("utf-8")).decode(),
        })
        body = ("Registers the IP233 Image and Video custom node collection.\n\n"
                + "Repository: " + entry["reference"] + "\n\n"
                + "Provides image generation/editing, video generation, native IMAGE/MASK/VIDEO outputs, and task recovery. "
                + "Requires an IP233 API key and paid service usage. MIT license. Dependencies are declared in requirements.txt and pyproject.toml. "
                + "Node classes use static NODE_CLASS_MAPPINGS. No runtime pip installs, bundled keys, or import-time network requests.\n\n"
                + "This PR changes only custom-node-list.json; generated node mappings are left to the Manager scanner.")
        result = api("POST", f"/repos/{UPSTREAM}/pulls", json={"title": "Add IP233 Image and Video nodes",
                     "head": owner + ":" + head_branch, "base": default_branch, "body": body})
        print("Created PR: " + result["html_url"])


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
