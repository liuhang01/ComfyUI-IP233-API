"""Bind real public GitHub and Comfy Registry identities, then validate release."""
import argparse
import json
import re
from pathlib import Path

import requests
import tomlkit

ROOT = Path(__file__).resolve().parents[1]


def manager_entry(repository, author):
    return {
        "author": author, "title": "IP233 Image and Video", "id": "ip233-ai-nodes",
        "reference": repository, "files": [repository], "install_type": "git-clone",
        "description": "Image generation/editing, video generation, native IMAGE/MASK/VIDEO outputs, and resumable tasks for IP233 Media API (https://new.ip233.com/). Requires an IP233 API key and paid API usage.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, help="Existing public GitHub repository URL")
    parser.add_argument("--publisher", help="Registered Comfy Registry publisher ID; optional for a Manager-only PR")
    parser.add_argument("--version", default="0.1.0")
    args = parser.parse_args()
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_-]+)/([A-Za-z0-9_.-]+)/?", args.repository)
    if not match or args.publisher and not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.publisher):
        parser.error("Provide a public GitHub URL and, if specified, a valid registered publisher ID.")
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        parser.error("Registry version must be X.Y.Z.")
    owner, repo = match.groups()
    repository = f"https://github.com/{owner}/{repo}"
    response = requests.get(f"https://api.github.com/repos/{owner}/{repo}", timeout=30)
    response.raise_for_status()
    metadata = response.json()
    if metadata.get("private") or metadata.get("archived"):
        parser.error("The repository must be public and active.")
    document = tomlkit.parse((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    document["project"]["version"] = args.version
    document["project"]["urls"]["Repository"] = repository
    if args.publisher:
        document["tool"]["comfy"]["PublisherId"] = args.publisher
    (ROOT / "pyproject.toml").write_text(tomlkit.dumps(document), encoding="utf-8")
    release_dir = ROOT / ".release"
    release_dir.mkdir(exist_ok=True)
    (release_dir / "manager-entry.json").write_text(json.dumps(manager_entry(repository, owner), indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {repository} v{args.version}; publisher={args.publisher or 'not configured (Manager-only)'}.")
    print("Publisher ownership and Registry token must still be verified by Comfy Registry during publication.")


if __name__ == "__main__":
    main()
