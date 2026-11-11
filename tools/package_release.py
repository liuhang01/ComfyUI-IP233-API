"""Create an installable source ZIP, explicitly excluding credentials and caches."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
try:
    import tomllib
except ImportError:
    import tomlkit as tomllib

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_FILES = {"__init__.py", "README.md", "LICENSE", "NOTICE", "requirements.txt",
                 "pyproject.toml", "MANIFEST.in", "ip233.local.example.json", ".gitignore"}
ALLOWED_DIRS = {"ip233", "tools", "tests", "docs", "examples", ".github"}


def main():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    destination = ROOT / "dist" / f"ComfyUI-IP233-API-{version}.zip"
    destination.parent.mkdir(exist_ok=True)
    count = 0
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or "__pycache__" in relative.parts or path.suffix in (".pyc", ".pyo"):
                continue
            if relative.parts[0] not in ALLOWED_DIRS and str(relative) not in ALLOWED_FILES:
                continue
            if relative.as_posix() == ".github/workflows/import-source.yml":
                continue
            archive.write(path, "ComfyUI-IP233-API/" + relative.as_posix())
            count += 1
    print(f"Packaged {count} source files: {destination}")


if __name__ == "__main__":
    main()
