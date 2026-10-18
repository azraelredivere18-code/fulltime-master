"""Create reviewable release archives from the verified Windows build."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT.parents[1] / "outputs"
DIST = ROOT / "dist" / "全职高手"
WINDOWS_ZIP = OUTPUTS / "全职高手_Windows_0.12.0.zip"
SOURCE_ZIP = OUTPUTS / "全职高手_源码_0.12.0.zip"


def add_file(archive: zipfile.ZipFile, source: Path, name: str) -> None:
    archive.write(source, name)


def main() -> None:
    if not (DIST / "全职高手.exe").is_file():
        raise SystemExit("Build the executable first")
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "REBUILD_REPORT.md", OUTPUTS / "全职高手_重构与验证报告_0.12.0.md")
    with zipfile.ZipFile(WINDOWS_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        add_file(archive, ROOT / "README.md", "README.md")
        add_file(archive, ROOT / "REBUILD_REPORT.md", "REBUILD_REPORT.md")
        for source in DIST.rglob("*"):
            if source.is_file():
                add_file(archive, source, str(Path(DIST.name) / source.relative_to(DIST)))

    with zipfile.ZipFile(SOURCE_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in ("app.py", "backend.py", "automation.py", "application_filters.py", "employment_type.py", "recruitment_track.py", "official_apply.py", "resume_import.py", "embedded_browser.py", "site_adapters.py", "site_automation.py", "sales_roles.py", "salary_codec.py", "scheduler.py", "build.py", "package.py", "requirements.txt", "README.md", "REBUILD_REPORT.md", "MIGRATION_STATUS.md", "PLATFORM_AUDIT_0.12.0.md"):
            add_file(archive, ROOT / name, name)
        for directory in ("config", "tests"):
            for source in (ROOT / directory).rglob("*"):
                if source.is_file() and source.suffix not in {".pyc"} and "__pycache__" not in source.parts:
                    add_file(archive, source, str(source.relative_to(ROOT)))
        for name in ("index.html", "setting.html", "record.html", "official.html"):
            source = ROOT / "stage-0.12" / "gui" / "templates" / name
            add_file(archive, source, str(Path("gui/templates") / name))
        static = ROOT / "stage-0.12" / "gui" / "templates" / "static"
        for source in static.rglob("*"):
            if source.is_file():
                add_file(archive, source, str(Path("gui/templates/static") / source.relative_to(static)))

    for path in (WINDOWS_ZIP, SOURCE_ZIP):
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                raise SystemExit(f"Archive damaged: {path}: {bad}")
        print(f"{path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
