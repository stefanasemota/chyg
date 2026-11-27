#!/usr/bin/env python3
"""Bundle src/context_hygiene into a standalone single-file ./chyg zipapp."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import zipapp
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SRC_PACKAGE = REPO_ROOT / "src" / "context_hygiene"
OUTPUT_BIN = REPO_ROOT / "chyg"


def build(output_path: Path = OUTPUT_BIN) -> Path:
    """Compile `src/context_hygiene` into a single-file zipapp executable."""
    if not SRC_PACKAGE.is_dir():
        raise FileNotFoundError(f"Package directory not found: {SRC_PACKAGE}")

    with tempfile.TemporaryDirectory(prefix="chyg-build-") as tmp_dir:
        staging_root = Path(tmp_dir)
        dest_pkg = staging_root / "context_hygiene"
        shutil.copytree(
            SRC_PACKAGE,
            dest_pkg,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store"),
        )

        zipapp.create_archive(
            source=staging_root,
            target=output_path,
            interpreter="/usr/bin/env python3",
            main="context_hygiene.cli:main",
            compressed=True,
        )

    current_mode = output_path.stat().st_mode
    output_path.chmod(
        current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )
    return output_path


def main() -> int:
    built = build()
    size_kb = os.path.getsize(built) / 1024.0
    print(f"Built {built} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
