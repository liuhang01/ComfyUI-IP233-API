"""Fail closed until the project is bound to real publication identities."""
import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomlkit as tomllib

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / "pyproject.toml"
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    project = document["project"]
    publisher = document.get("tool", {}).get("comfy", {}).get("PublisherId", "")
    repository = project.get("urls", {}).get("Repository", "")
    errors = []
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", repository):
        errors.append("Missing real public Repository URL.")
    if not publisher or publisher.lower() in ("your-publisher", "placeholder", "real_registered_publisher"):
        errors.append("Missing registered Comfy Registry PublisherId.")
    if not re.fullmatch(r"\d+\.\d+\.\d+", project["version"]):
        errors.append("Version must be X.Y.Z.")
    for name in ("__init__.py", "LICENSE", "README.md", "requirements.txt", "ip233/catalog.snapshot.json"):
        if not (ROOT / name).is_file():
            errors.append("Missing release file: " + name)
    if errors:
        print("Release is not configured:\n" + "\n".join(errors), file=sys.stderr)
        return 1
    print(f"Release configuration valid: {project['name']} v{project['version']}, publisher={publisher}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
