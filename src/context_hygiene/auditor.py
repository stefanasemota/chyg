"""Deterministic 5-rule context hygiene auditor and safe remediation engine."""

from __future__ import annotations

import datetime
import difflib
import fnmatch
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for Python 3.9/3.10
    tomllib = None  # type: ignore[assignment]


DEFAULT_ALWAYS_ON_MAX_LINES = 150
DEFAULT_SKILL_MAX_LINES = 300
DEFAULT_STALE_DAYS = 120

ALWAYS_ON_FILENAMES: frozenset[str] = frozenset(
    {
        "AGENTS.md",
        "CLAUDE.md",
        ".cursorrules",
        ".windsurfrules",
        "copilot-instructions.md",
    }
)

FLUFF_PHRASES: tuple[str, ...] = (
    "write clean code",
    "do not hallucinate",
    "don't hallucinate",
    "never hallucinate",
    "handle all edge cases",
    "think step by step",
    "follow best practices",
    "write bug-free code",
    "ensure high quality",
    "be concise and helpful",
    "act as an expert",
    "you are an expert",
)

LINTER_CONFIG_PATTERNS: tuple[tuple[str, str], ...] = (
    (".prettierrc", "Prettier"),
    (".prettierrc.json", "Prettier"),
    (".prettierrc.yml", "Prettier"),
    (".prettierrc.yaml", "Prettier"),
    (".prettierrc.js", "Prettier"),
    (".prettierrc.cjs", "Prettier"),
    (".prettierrc.mjs", "Prettier"),
    ("prettier.config.js", "Prettier"),
    ("prettier.config.mjs", "Prettier"),
    ("biome.json", "Biome"),
    ("biome.jsonc", "Biome"),
    (".eslintrc", "ESLint"),
    (".eslintrc.json", "ESLint"),
    (".eslintrc.js", "ESLint"),
    (".eslintrc.cjs", "ESLint"),
    (".eslintrc.yml", "ESLint"),
    (".eslintrc.yaml", "ESLint"),
    ("eslint.config.js", "ESLint"),
    ("eslint.config.mjs", "ESLint"),
    ("eslint.config.ts", "ESLint"),
    ("ruff.toml", "Ruff"),
    (".ruff.toml", "Ruff"),
    (".swiftformat", "SwiftFormat"),
)

FORMATTING_OVERLAP_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "indentation",
        re.compile(
            r"\b(?:use\s+(?:2|4)\s+spaces|indent(?:ation)?\s+(?:with|using)\s+(?:\d+\s+spaces|tabs)|use\s+tabs\s+for\s+indentation)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "quotes",
        re.compile(
            r"\b(?:use|prefer|always\s+use)\s+(?:single|double)\s+quotes?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "semicolons",
        re.compile(
            r"\b(?:no\s+semicolons?|omit\s+semicolons?|never\s+use\s+semicolons?|always\s+use\s+semicolons?|require\s+semicolons?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "line-length",
        re.compile(
            r"\b(?:max(?:imum)?\s+line\s+length|line\s+length\s+(?:of|limit)|wrap\s+lines?\s+at\s+\d+|keep\s+lines?\s+under\s+\d+\s+(?:chars?|characters?))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "trailing-commas",
        re.compile(
            r"\b(?:use|prefer|omit|no|always\s+include)\s+trailing\s+commas?\b",
            re.IGNORECASE,
        ),
    ),
)

# Backticked inline code spans (single backticks, non-empty).
INLINE_BACKTICK_RE = re.compile(r"`([^`\n]+)`")

# Script command patterns inside backticks or prose.
NPM_RUN_RE = re.compile(r"\bnpm\s+run\s+([A-Za-z0-9:_\-\.]+)")
MAKE_TARGET_RE = re.compile(r"\bmake\s+([A-Za-z0-9_\-\.]+)")
PYPROJECT_SCRIPT_RE = re.compile(r"\b(?:poetry|uv)\s+run\s+([A-Za-z0-9_\-\.]+)")

KNOWN_FILE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".md",
        ".mdc",
        ".sh",
        ".bash",
        ".zsh",
        ".go",
        ".rs",
        ".swift",
        ".kt",
        ".java",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".css",
        ".scss",
        ".html",
        ".sql",
        ".txt",
        ".cfg",
        ".ini",
        ".env",
        ".lock",
    }
)


@dataclass
class AuditConfig:
    """Configuration for context hygiene thresholds and ignores."""

    always_on_max_lines: int = DEFAULT_ALWAYS_ON_MAX_LINES
    skill_max_lines: int = DEFAULT_SKILL_MAX_LINES
    stale_days: int = DEFAULT_STALE_DAYS
    ignore_paths: list[str] = field(default_factory=list)
    ignore_rules: list[str] = field(default_factory=list)
    extra_fluff_phrases: list[str] = field(default_factory=list)


@dataclass
class Finding:
    """A single hygiene rule violation."""

    rule_id: str
    severity: str  # "warning" | "error"
    message: str
    line: Optional[int] = None
    detail: Optional[str] = None
    fixable: bool = False


@dataclass
class FileAuditResult:
    """Audit result for a single instruction or skill file."""

    path: Path
    relative_path: str
    category: str  # "always_on" | "on_demand"
    line_count: int
    word_count: int
    estimated_tokens: int
    age_days: Optional[int]
    last_modified_source: str  # "git" | "mtime"
    findings: list[Finding] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(f.rule_id == "dead-path" for f in self.findings):
            return "broken"
        if self.findings:
            return "warning"
        return "lean"


@dataclass
class AuditReport:
    """Aggregated audit report across all discovered files."""

    root: Path
    results: list[FileAuditResult] = field(default_factory=list)
    skipped_protected: list[Path] = field(default_factory=list)
    skipped_symlinks: list[Path] = field(default_factory=list)
    skipped_unreadable: list[Path] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return sum(r.estimated_tokens for r in self.results)

    @property
    def lean_results(self) -> list[FileAuditResult]:
        return [r for r in self.results if r.status == "lean"]

    @property
    def warning_results(self) -> list[FileAuditResult]:
        return [r for r in self.results if r.status == "warning"]

    @property
    def broken_results(self) -> list[FileAuditResult]:
        return [r for r in self.results if r.status == "broken"]


def load_config(repo_root: Path, stale_days_override: Optional[int] = None) -> AuditConfig:
    """Load optional `.context-hygiene.json` from `repo_root`."""
    config = AuditConfig()
    cfg_path = repo_root / ".context-hygiene.json"
    if cfg_path.is_file() and os.access(str(cfg_path), os.R_OK):
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            if isinstance(data.get("always_on_max_lines"), int):
                config.always_on_max_lines = data["always_on_max_lines"]
            if isinstance(data.get("skill_max_lines"), int):
                config.skill_max_lines = data["skill_max_lines"]
            if isinstance(data.get("stale_days"), int):
                config.stale_days = data["stale_days"]
            if isinstance(data.get("ignore_paths"), list):
                config.ignore_paths = [str(p) for p in data["ignore_paths"]]
            if isinstance(data.get("ignore_rules"), list):
                config.ignore_rules = [str(r) for r in data["ignore_rules"]]
            if isinstance(data.get("extra_fluff_phrases"), list):
                config.extra_fluff_phrases = [str(p) for p in data["extra_fluff_phrases"]]

    if stale_days_override is not None:
        config.stale_days = stale_days_override
    return config


def parse_frontmatter(text: str) -> tuple[dict[str, Any], int]:
    """Parse minimal YAML frontmatter from `text`.

    Returns `(metadata_dict, body_start_line_index)` where `body_start_line_index`
    is 0-based.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, 0

    end_idx: Optional[int] = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return {}, 0

    meta: dict[str, Any] = {}
    for raw_line in lines[1:end_idx]:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, raw_val = stripped.split(":", 1)
        key = key.strip()
        val = raw_val.strip().strip('"').strip("'")
        if val.startswith("[") and val.endswith("]"):
            items = [
                item.strip().strip('"').strip("'")
                for item in val[1:-1].split(",")
                if item.strip()
            ]
            meta[key] = items
        elif re.fullmatch(r"\d+", val):
            meta[key] = int(val)
        else:
            meta[key] = val

    return meta, end_idx + 1


def _get_file_age_days(
    file_path: Path, repo_root: Path, now_ts: Optional[float] = None
) -> tuple[Optional[int], str]:
    """Return `(age_days, source)` using git commit time, falling back to mtime."""
    now = now_ts if now_ts is not None else time.time()
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(file_path)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if proc.returncode == 0:
            raw_ts = proc.stdout.strip()
            if raw_ts.isdigit():
                commit_ts = int(raw_ts)
                age = max(0, int((now - commit_ts) // 86400))
                return age, "git"
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        mtime = file_path.stat().st_mtime
        age = max(0, int((now - mtime) // 86400))
        return age, "mtime"
    except OSError:
        return None, "mtime"


def detect_project_linters(repo_root: Path) -> list[str]:
    """Detect formatting/linting tools configured in `repo_root`."""
    found: list[str] = []
    seen: set[str] = set()

    for filename, tool_name in LINTER_CONFIG_PATTERNS:
        if (repo_root / filename).exists() and tool_name not in seen:
            seen.add(tool_name)
            found.append(tool_name)

    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file() and os.access(str(pyproject), os.R_OK):
        try:
            content = pyproject.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""
        for section, tool_name in (
            ("[tool.ruff", "Ruff"),
            ("[tool.black", "Black"),
            ("[tool.isort", "isort"),
            ("[tool.flake8", "Flake8"),
        ):
            if section in content and tool_name not in seen:
                seen.add(tool_name)
                found.append(tool_name)

    return found


def _load_package_json_scripts(repo_root: Path) -> Optional[set[str]]:
    pkg = repo_root / "package.json"
    if not pkg.is_file() or not os.access(str(pkg), os.R_OK):
        return None
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    scripts = data.get("scripts")
    if isinstance(scripts, dict):
        return set(scripts.keys())
    return set()


def _load_makefile_targets(repo_root: Path) -> Optional[set[str]]:
    makefile = repo_root / "Makefile"
    if not makefile.is_file() or not os.access(str(makefile), os.R_OK):
        return None
    try:
        text = makefile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    targets: set[str] = set()
    for line in text.splitlines():
        if line.startswith(("\t", " ", "#", ".")):
            continue
        match = re.match(r"^([A-Za-z0-9_\-\.]+)\s*:(?!=)", line)
        if match:
            targets.add(match.group(1))
    return targets


def _load_pyproject_scripts(repo_root: Path) -> Optional[set[str]]:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file() or not os.access(str(pyproject), os.R_OK):
        return None
    try:
        raw_bytes = pyproject.read_bytes()
    except OSError:
        return None

    scripts: set[str] = set()
    if tomllib is not None:
        try:
            data = tomllib.loads(raw_bytes.decode("utf-8", errors="replace"))
        except Exception:
            data = {}
        project_scripts = data.get("project", {}).get("scripts", {})
        if isinstance(project_scripts, dict):
            scripts.update(project_scripts.keys())
        poetry_scripts = data.get("tool", {}).get("poetry", {}).get("scripts", {})
        if isinstance(poetry_scripts, dict):
            scripts.update(poetry_scripts.keys())
        pdm_scripts = data.get("tool", {}).get("pdm", {}).get("scripts", {})
        if isinstance(pdm_scripts, dict):
            scripts.update(pdm_scripts.keys())
        return scripts

    # Lightweight fallback for Python 3.9/3.10 without tomllib.
    text = raw_bytes.decode("utf-8", errors="replace")
    in_scripts_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_scripts_section = stripped in (
                "[project.scripts]",
                "[tool.poetry.scripts]",
                "[tool.pdm.scripts]",
            )
            continue
        if in_scripts_section and "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip().strip('"').strip("'")
            if key:
                scripts.add(key)
    return scripts


def _looks_like_relative_path(token: str) -> bool:
    """Heuristically decide whether a backticked token is a local relative path."""
    candidate = token.strip()
    if not candidate or len(candidate) > 200:
        return False
    # Exclude whitespace, URLs, flags, env vars, home/absolute paths, templates, globs.
    if any(ch.isspace() for ch in candidate):
        return False
    if candidate.startswith(
        ("http://", "https://", "mailto:", "file://", "/", "~", "$", "-", "@")
    ):
        return False
    if any(ch in candidate for ch in ("*", "?", "<", ">", "{", "}", "|", ":")):
        return False
    if candidate in (".", ".."):
        return False

    # Must either contain a slash (like src/app.py or docs/guide) or end with a known extension.
    if "/" in candidate:
        # Avoid fractions or ratios like `a/b` where neither looks like a path segment with extension
        # or typical directory name, e.g., `y/N` or `CI/CD`.
        parts = [p for p in candidate.split("/") if p]
        if len(parts) == 2 and parts[0].isupper() and parts[1].isupper():
            return False
        if candidate in ("y/N", "Y/n", "yes/no", "on/off", "true/false"):
            return False
        return True

    suffix = Path(candidate).suffix.lower()
    if suffix in KNOWN_FILE_EXTENSIONS and not candidate.startswith("."):
        return True
    return False


def _strip_line_anchor(token: str) -> str:
    """Strip `#L10` or `:10` suffix from a path token if present."""
    if "#" in token:
        token = token.split("#", 1)[0]
    return token.rstrip("/")


def _iter_non_fenced_lines(
    lines: list[str], start_index: int = 0
) -> list[tuple[int, str]]:
    """Return `(1_based_line_number, line_text)` outside fenced code blocks."""
    out: list[tuple[int, str]] = []
    in_fence = False
    for idx in range(start_index, len(lines)):
        line = lines[idx]
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append((idx + 1, line))
    return out


def _is_ignored(rel_path: str, ignore_paths: Sequence[str]) -> bool:
    for pattern in ignore_paths:
        if fnmatch.fnmatch(rel_path, pattern) or rel_path == pattern:
            return True
    return False


def audit_file(
    file_path: Path,
    repo_root: Path,
    config: AuditConfig,
    *,
    linters: Optional[list[str]] = None,
    pkg_scripts: Optional[set[str]] = None,
    make_targets: Optional[set[str]] = None,
    pyproject_scripts: Optional[set[str]] = None,
    now_ts: Optional[float] = None,
) -> FileAuditResult:
    """Audit a single instruction file against all 5 deterministic rules."""
    text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    line_count = len(lines)
    word_count = len(text.split())
    estimated_tokens = int(round(word_count * 1.3))

    try:
        rel_path = str(file_path.relative_to(repo_root))
    except ValueError:
        rel_path = str(file_path)

    category = (
        "always_on" if file_path.name in ALWAYS_ON_FILENAMES else "on_demand"
    )
    meta, body_start = parse_frontmatter(text)
    age_days, age_source = _get_file_age_days(file_path, repo_root, now_ts=now_ts)

    ignored_rules = set(config.ignore_rules)
    fm_ignored = meta.get("ignore_rules")
    if isinstance(fm_ignored, list):
        ignored_rules.update(str(r) for r in fm_ignored)

    findings: list[Finding] = []

    # Rule 1: Context Budget (Token Bloat)
    if "context-budget" not in ignored_rules:
        default_limit = (
            config.always_on_max_lines
            if category == "always_on"
            else config.skill_max_lines
        )
        max_lines = (
            meta["max_lines"]
            if isinstance(meta.get("max_lines"), int)
            else default_limit
        )
        if line_count > max_lines:
            findings.append(
                Finding(
                    rule_id="context-budget",
                    severity="warning",
                    message=(
                        f"Exceeds {category.replace('_', '-')} budget: "
                        f"{line_count} lines (limit: {max_lines})"
                    ),
                )
            )

    # Rule 2: Staleness / Capability Creep
    if "staleness" not in ignored_rules:
        now_date = datetime.datetime.fromtimestamp(
            now_ts if now_ts is not None else time.time(),
            tz=datetime.timezone.utc,
        ).date()
        review_after_raw = meta.get("review_after")
        checked_review_after = False
        if isinstance(review_after_raw, str):
            try:
                review_date = datetime.date.fromisoformat(review_after_raw)
                checked_review_after = True
                if now_date > review_date:
                    findings.append(
                        Finding(
                            rule_id="staleness",
                            severity="warning",
                            message=(
                                f"Past frontmatter review_after date ({review_after_raw}); "
                                "run an ablation check on current models"
                            ),
                        )
                    )
            except ValueError:
                pass

        if not checked_review_after and age_days is not None and age_days > config.stale_days:
            findings.append(
                Finding(
                    rule_id="staleness",
                    severity="warning",
                    message=(
                        f"Untouched for {age_days} days (threshold: {config.stale_days}, "
                        f"via {age_source}); review for capability creep"
                    ),
                )
            )

    non_fenced = _iter_non_fenced_lines(lines, start_index=body_start)

    # Rule 3: Dead Local References
    if "dead-path" not in ignored_rules:
        for line_no, line in non_fenced:
            # 3a. Backticked relative paths
            for match in INLINE_BACKTICK_RE.finditer(line):
                raw_token = match.group(1).strip()
                # Check if the backticked span is a command like `npm run build`
                if raw_token.startswith(("npm run ", "make ", "poetry run ", "uv run ")):
                    continue
                clean_token = _strip_line_anchor(raw_token)
                if not _looks_like_relative_path(clean_token):
                    continue
                target_from_root = repo_root / clean_token
                target_from_file = file_path.parent / clean_token
                if not target_from_root.exists() and not target_from_file.exists():
                    findings.append(
                        Finding(
                            rule_id="dead-path",
                            severity="error",
                            message=f"Dead local path reference: `{clean_token}`",
                            line=line_no,
                            detail=clean_token,
                            fixable=True,
                        )
                    )

            # 3b. Script commands (`npm run <script>`, `make <target>`, `poetry/uv run <script>`)
            if pkg_scripts is not None:
                for m in NPM_RUN_RE.finditer(line):
                    script_name = m.group(1)
                    if script_name not in pkg_scripts:
                        findings.append(
                            Finding(
                                rule_id="dead-path",
                                severity="error",
                                message=f"Missing package.json script: `npm run {script_name}`",
                                line=line_no,
                                detail=f"npm run {script_name}",
                                fixable=True,
                            )
                        )

            if make_targets is not None:
                for m in MAKE_TARGET_RE.finditer(line):
                    target_name = m.group(1)
                    if target_name.startswith("-"):
                        continue
                    if target_name not in make_targets:
                        findings.append(
                            Finding(
                                rule_id="dead-path",
                                severity="error",
                                message=f"Missing Makefile target: `make {target_name}`",
                                line=line_no,
                                detail=f"make {target_name}",
                                fixable=True,
                            )
                        )

            if pyproject_scripts is not None and pyproject_scripts:
                for m in PYPROJECT_SCRIPT_RE.finditer(line):
                    script_name = m.group(1)
                    # Only flag if it's not a common built-in CLI tool like pytest/python/ruff
                    if script_name not in pyproject_scripts and script_name not in {
                        "python",
                        "python3",
                        "pytest",
                        "ruff",
                        "mypy",
                        "black",
                        "flake8",
                    }:
                        findings.append(
                            Finding(
                                rule_id="dead-path",
                                severity="error",
                                message=f"Missing pyproject.toml script: `{m.group(0)}`",
                                line=line_no,
                                detail=m.group(0),
                                fixable=True,
                            )
                        )

    # Rule 4: Low-Signal Prompt Fluff
    if "prompt-fluff" not in ignored_rules:
        phrases = list(FLUFF_PHRASES) + list(config.extra_fluff_phrases)
        for line_no, line in non_fenced:
            lowered = line.lower()
            for phrase in phrases:
                if phrase.lower() in lowered:
                    findings.append(
                        Finding(
                            rule_id="prompt-fluff",
                            severity="warning",
                            message=f'Low-signal prompt fluff: "{phrase}"',
                            line=line_no,
                            detail=phrase,
                        )
                    )
                    break

    # Rule 5: Deterministic Linter Overlap
    detected_linters = linters if linters is not None else detect_project_linters(repo_root)
    if "linter-overlap" not in ignored_rules and detected_linters:
        linter_label = ", ".join(detected_linters)
        for line_no, line in non_fenced:
            for rule_topic, pattern in FORMATTING_OVERLAP_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        Finding(
                            rule_id="linter-overlap",
                            severity="warning",
                            message=(
                                f"Formatting rule ({rule_topic}) duplicates existing "
                                f"linter/formatter config ({linter_label})"
                            ),
                            line=line_no,
                            detail=rule_topic,
                        )
                    )
                    break

    return FileAuditResult(
        path=file_path,
        relative_path=rel_path,
        category=category,
        line_count=line_count,
        word_count=word_count,
        estimated_tokens=estimated_tokens,
        age_days=age_days,
        last_modified_source=age_source,
        findings=findings,
    )


def audit_files(
    files: Sequence[Path],
    repo_root: Path,
    *,
    stale_days_override: Optional[int] = None,
    now_ts: Optional[float] = None,
    skipped_protected: Optional[list[Path]] = None,
    skipped_symlinks: Optional[list[Path]] = None,
    skipped_unreadable: Optional[list[Path]] = None,
) -> AuditReport:
    """Audit a collection of discovered instruction files."""
    config = load_config(repo_root, stale_days_override=stale_days_override)
    linters = detect_project_linters(repo_root)
    pkg_scripts = _load_package_json_scripts(repo_root)
    make_targets = _load_makefile_targets(repo_root)
    pyproject_scripts = _load_pyproject_scripts(repo_root)

    report = AuditReport(
        root=repo_root,
        skipped_protected=list(skipped_protected or []),
        skipped_symlinks=list(skipped_symlinks or []),
        skipped_unreadable=list(skipped_unreadable or []),
    )

    for file_path in files:
        try:
            rel_path = str(file_path.relative_to(repo_root))
        except ValueError:
            rel_path = str(file_path)

        if _is_ignored(rel_path, config.ignore_paths):
            continue

        result = audit_file(
            file_path,
            repo_root,
            config,
            linters=linters,
            pkg_scripts=pkg_scripts,
            make_targets=make_targets,
            pyproject_scripts=pyproject_scripts,
            now_ts=now_ts,
        )
        report.results.append(result)

    return report


def remediate_dead_paths(
    report: AuditReport, *, write_backup: bool = True
) -> dict[Path, str]:
    """Safely strip lines with verified dead-path findings.

    Writes a `.bak` backup alongside each modified file (when `write_backup=True`)
    and returns a mapping of `file_path -> unified_diff`.
    """
    diffs: dict[Path, str] = {}
    for res in report.results:
        dead_lines = {
            f.line
            for f in res.findings
            if f.rule_id == "dead-path" and f.fixable and f.line is not None
        }
        if not dead_lines:
            continue

        original_text = res.path.read_text(encoding="utf-8", errors="replace")
        original_lines = original_text.splitlines(keepends=True)
        new_lines = [
            line
            for idx, line in enumerate(original_lines, start=1)
            if idx not in dead_lines
        ]

        if new_lines == original_lines:
            continue

        if write_backup:
            backup_path = res.path.with_name(res.path.name + ".bak")
            backup_path.write_text(original_text, encoding="utf-8")

        res.path.write_text("".join(new_lines), encoding="utf-8")

        diff = "".join(
            difflib.unified_diff(
                original_lines,
                new_lines,
                fromfile=f"a/{res.relative_path}",
                tofile=f"b/{res.relative_path}",
            )
        )
        diffs[res.path] = diff

    return diffs
