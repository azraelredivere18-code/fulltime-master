"""Stage the verified interface and build a standalone Windows distribution."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "stage-0.14"
TEMPLATES = ROOT / "gui" / "templates"


def stage_assets() -> None:
    target = STAGE / "gui" / "templates"
    for name in ("index.html", "setting.html", "record.html", "official.html"):
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TEMPLATES / name, destination)
    for source in (TEMPLATES / "static").rglob("*"):
        if (not source.is_file() or source.name == "activation.js" or
            source.relative_to(TEMPLATES / "static").parts[0] in {"images", "fonts"} or
            source.name == "icon.css"):
            continue
        destination = target / "static" / source.relative_to(TEMPLATES / "static")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    for source in (ROOT / "config").rglob("*.json"):
        destination = STAGE / "config" / source.relative_to(ROOT / "config")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main() -> int:
    if sys.platform != "win32":
        raise SystemExit("This distribution target is Windows")
    stage_assets()
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed",
        "--name", "全职高手", "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "pyinstaller-build"),
        "--specpath", str(ROOT),
        "--add-data", f"{STAGE / 'gui'};gui",
        "--add-data", f"{STAGE / 'config'};config",
        "--hidden-import", "automation",
        "--hidden-import", "application_filters",
        "--hidden-import", "sales_roles",
        "--hidden-import", "salary_codec",
        "--hidden-import", "embedded_browser",
        "--hidden-import", "site_adapters",
        "--hidden-import", "site_automation",
        "--hidden-import", "employment_type",
        "--hidden-import", "recruitment_track",
        "--hidden-import", "official_apply",
        "--hidden-import", "resume_import",
        "--hidden-import", "scheduler",
        "--collect-all", "webview",
        str(ROOT / "app.py"),
    ]
    # Conda's Python extensions depend on DLLs kept under Library/bin. PyInstaller
    # may not discover that directory from a venv created with Conda Python.
    conda_bin = Path(sys.base_prefix) / "Library" / "bin"
    for name in ("ffi.dll", "sqlite3.dll"):
        candidate = conda_bin / name
        if candidate.is_file():
            command[-1:-1] = ["--add-binary", f"{candidate};."]
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
