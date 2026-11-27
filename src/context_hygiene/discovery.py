"""macOS TCC-safe path discovery and symlink boundary checks."""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence, Set

PROTECTED_HOME_SUBDIRS: frozenset[str] = frozenset(
    {"Desktop", "Documents", "Downloads", "Library"}
)

STANDARD_AGENT_RELATIVE_PATHS: tuple[str, ...] = (
    ".claude",
    ".cursor",
    ".codex",
    ".config/opencode",
)

IGNORED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".next",
        ".turbo",
        "target",
        ".cache",
    }
)

ROOT_INSTRUCTION_FILENAMES: frozenset[str] = frozenset(
    {
        "AGENTS.md",
        "CLAUDE.md",
        ".cursorrules",
        ".windsurfrules",
    }
)


@dataclass
class DiscoveryResult:
    """Result of a TCC-safe instruction file discovery pass."""

    roots: list[Path] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    skipped_protected: list[Path] = field(default_factory=list)
    skipped_symlinks: list[Path] = field(default_factory=list)
    skipped_unreadable: list[Path] = field(default_factory=list)


def is_macos() -> bool:
    """Return True when running on macOS (Darwin)."""
    return platform.system() == "Darwin"


def detect_git_root(cwd: Optional[Path] = None) -> Optional[Path]:
    """Return the Git repository root for `cwd`, or None if not in a repo."""
    start = Path(cwd) if cwd is not None else Path.cwd()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    output = proc.stdout.strip()
    return Path(output) if output else None


def standard_agent_config_paths(home: Optional[Path] = None) -> list[Path]:
    """Return standard AI agent config directories under `home`."""
    base = Path(home) if home is not None else Path.home()
    return [base / rel for rel in STANDARD_AGENT_RELATIVE_PATHS]


def _resolve_safe(path: Path) -> Optional[Path]:
    """Resolve `path` without raising on permission or loop errors."""
    try:
        return path.resolve(strict=False)
    except OSError:
        return None


def is_within_root(candidate: Path, root: Path) -> bool:
    """Return True if `candidate` resolves inside (or equal to) `root`."""
    resolved_root = _resolve_safe(root)
    resolved_candidate = _resolve_safe(candidate)
    if resolved_root is None or resolved_candidate is None:
        return False
    try:
        resolved_candidate.relative_to(resolved_root)
        return True
    except ValueError:
        return False


def get_protected_paths(home: Optional[Path] = None) -> list[Path]:
    """Return $HOME and macOS TCC-protected subdirectories."""
    base = _resolve_safe(Path(home) if home is not None else Path.home())
    if base is None:
        return []
    return [base] + [base / name for name in sorted(PROTECTED_HOME_SUBDIRS)]


def is_protected_path(
    path: Path,
    home: Optional[Path] = None,
    explicit_roots: Optional[Iterable[Path]] = None,
) -> bool:
    """Return True if `path` is $HOME or a TCC-protected dir not explicitly allowed.

    A protected directory is permitted only when the user explicitly selected
    that directory (or a subdirectory inside it) as a scan root.
    """
    base = _resolve_safe(Path(home) if home is not None else Path.home())
    resolved = _resolve_safe(path)
    if base is None or resolved is None:
        return False

    explicit_resolved: Set[Path] = set()
    if explicit_roots:
        for er in explicit_roots:
            r = _resolve_safe(er)
            if r is not None:
                explicit_resolved.add(r)

    if resolved == base:
        return resolved not in explicit_resolved

    for name in PROTECTED_HOME_SUBDIRS:
        protected_dir = base / name
        if resolved == protected_dir:
            return resolved not in explicit_resolved
        try:
            resolved.relative_to(protected_dir)
        except ValueError:
            continue
        # `resolved` is inside a protected dir; allow only if an explicit root
        # covers `resolved` (either equals protected_dir or is an ancestor of resolved).
        for er in explicit_resolved:
            try:
                resolved.relative_to(er)
                # Ensure the explicit root isn't broader than the protected dir (e.g., $HOME
                # shouldn't silently unlock ~/Library unless ~/Library itself was selected).
                if er != base:
                    return False
            except ValueError:
                continue
        return True

    return False


def is_instruction_file(path: Path, scan_root: Path) -> bool:
    """Return True if `path` matches a supported AI instruction or skill file."""
    name = path.name
    if name in ROOT_INSTRUCTION_FILENAMES:
        return True
    if name == "SKILL.md":
        return True
    if name == "copilot-instructions.md" and path.parent.name == ".github":
        return True
    if path.suffix == ".mdc":
        parts = path.parts
        for idx in range(len(parts) - 2):
            if parts[idx] == ".cursor" and parts[idx + 1] == "rules":
                return True
    return False


def _is_readable(path: Path) -> bool:
    """Check read permission safely before opening."""
    try:
        return os.access(str(path), os.R_OK)
    except OSError:
        return False


def discover_instruction_files(
    roots: Sequence[Path],
    *,
    home: Optional[Path] = None,
    allow_protected: bool = False,
) -> DiscoveryResult:
    """Discover AI instruction files across `roots` with strict TCC & symlink safety.

    - Never walks $HOME, ~/Desktop, ~/Documents, ~/Downloads, or ~/Library
      unless `allow_protected=True`.
    - Never follows symlinks pointing outside the confirmed scan root.
    - Checks `os.access(..., os.R_OK)` and catches `PermissionError`.
    """
    result = DiscoveryResult()
    seen_files: Set[Path] = set()
    base_home = Path(home) if home is not None else Path.home()

    explicit_roots: Set[Path] = set()
    if allow_protected:
        for r in roots:
            resolved = _resolve_safe(r)
            if resolved is not None:
                explicit_roots.add(resolved)

    for raw_root in roots:
        root = Path(raw_root).expanduser()
        if not root.exists():
            continue

        if is_protected_path(root, home=base_home, explicit_roots=explicit_roots):
            result.skipped_protected.append(root)
            continue

        if not _is_readable(root):
            result.skipped_unreadable.append(root)
            continue

        resolved_root = _resolve_safe(root)
        if resolved_root is None:
            result.skipped_unreadable.append(root)
            continue

        result.roots.append(resolved_root)

        if resolved_root.is_file():
            if is_instruction_file(resolved_root, resolved_root.parent):
                if resolved_root not in seen_files:
                    seen_files.add(resolved_root)
                    result.files.append(resolved_root)
            continue

        def _on_walk_error(err: OSError) -> None:
            if err.filename:
                result.skipped_unreadable.append(Path(err.filename))

        for dirpath, dirnames, filenames in os.walk(
            str(resolved_root), followlinks=False, onerror=_on_walk_error
        ):
            current_dir = Path(dirpath)

            # Prune ignored, protected, unreadable, or escaping-symlink directories.
            kept_dirs: list[str] = []
            for dname in sorted(dirnames):
                if dname in IGNORED_DIR_NAMES:
                    continue
                candidate_dir = current_dir / dname

                if candidate_dir.is_symlink():
                    # Never follow symlinks pointing outside the scan root.
                    if not is_within_root(candidate_dir, resolved_root):
                        result.skipped_symlinks.append(candidate_dir)
                    else:
                        # Even for in-root directory symlinks, avoid cycles by not descending.
                        result.skipped_symlinks.append(candidate_dir)
                    continue

                if is_protected_path(
                    candidate_dir, home=base_home, explicit_roots=explicit_roots
                ):
                    result.skipped_protected.append(candidate_dir)
                    continue

                if not _is_readable(candidate_dir):
                    result.skipped_unreadable.append(candidate_dir)
                    continue

                kept_dirs.append(dname)

            dirnames[:] = kept_dirs

            for fname in sorted(filenames):
                candidate_file = current_dir / fname
                if not is_instruction_file(candidate_file, resolved_root):
                    continue

                if candidate_file.is_symlink():
                    if not is_within_root(candidate_file, resolved_root):
                        result.skipped_symlinks.append(candidate_file)
                        continue
                    if not candidate_file.exists():
                        result.skipped_symlinks.append(candidate_file)
                        continue

                if not _is_readable(candidate_file):
                    result.skipped_unreadable.append(candidate_file)
                    continue

                resolved_file = _resolve_safe(candidate_file)
                if resolved_file is None:
                    result.skipped_unreadable.append(candidate_file)
                    continue

                if not is_within_root(resolved_file, resolved_root):
                    result.skipped_symlinks.append(candidate_file)
                    continue

                if resolved_file not in seen_files:
                    seen_files.add(resolved_file)
                    result.files.append(resolved_file)

    result.files.sort()
    return result
