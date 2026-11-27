"""CLI flag parser, non-interactive audit runner, and atomic self-update."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Sequence

from context_hygiene import DEFAULT_UPDATE_URL, __version__
from context_hygiene.auditor import AuditReport, audit_files, remediate_dead_paths
from context_hygiene.discovery import (
    detect_git_root,
    discover_instruction_files,
    is_protected_path,
    standard_agent_config_paths,
)
from context_hygiene.reporter import format_json_report, format_terminal_report


def confirm_scope(targets: Sequence[Path], *, auto_yes: bool = False) -> bool:
    """Display exact target paths and require explicit `y/N` confirmation."""
    if auto_yes:
        return True
    print("The following paths outside the current Git repository will be scanned:")
    for t in targets:
        status = "exists" if t.exists() else "missing"
        print(f"  - {t} ({status})")
    try:
        answer = input("Proceed? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


def _resolve_audit_targets(
    *,
    path_arg: Optional[str],
    global_scan: bool,
    auto_yes: bool,
) -> tuple[Optional[Path], list[Path], bool]:
    """Return `(report_root, scan_roots, allow_protected)`.

    Returns `(None, [], False)` if the user declines scope confirmation.
    """
    if global_scan:
        targets = standard_agent_config_paths()
        if not confirm_scope(targets, auto_yes=auto_yes):
            return None, [], False
        existing = [p for p in targets if p.exists()]
        return Path.home(), existing, False

    if path_arg:
        target = Path(path_arg).expanduser().resolve()
        git_root = detect_git_root()
        outside_repo = git_root is None or not str(target).startswith(str(git_root))
        protected = is_protected_path(target)
        if outside_repo or protected:
            if not confirm_scope([target], auto_yes=auto_yes):
                return None, [], False
        return target, [target], protected

    git_root = detect_git_root()
    root = git_root if git_root is not None else Path.cwd()
    return root, [root], False


def run_audit(
    *,
    path_arg: Optional[str] = None,
    global_scan: bool = False,
    auto_yes: bool = False,
    strict: bool = False,
    as_json: bool = False,
    stale_days: Optional[int] = None,
    apply_fix: bool = False,
) -> int:
    """Execute a non-interactive audit and print the report."""
    report_root, scan_roots, allow_protected = _resolve_audit_targets(
        path_arg=path_arg,
        global_scan=global_scan,
        auto_yes=auto_yes,
    )
    if report_root is None:
        print("Scan cancelled.")
        return 0

    discovery = discover_instruction_files(
        scan_roots, allow_protected=allow_protected
    )
    report: AuditReport = audit_files(
        discovery.files,
        report_root,
        stale_days_override=stale_days,
        skipped_protected=discovery.skipped_protected,
        skipped_symlinks=discovery.skipped_symlinks,
        skipped_unreadable=discovery.skipped_unreadable,
    )

    if as_json:
        print(format_json_report(report))
    else:
        use_color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        print(format_terminal_report(report, use_color=use_color))

    if apply_fix and report.broken_results:
        diffs = remediate_dead_paths(report, write_backup=True)
        if not as_json:
            print("")
            print(f"Applied safe dead-path remediation to {len(diffs)} file(s) (.bak backups written):")
            for diff_text in diffs.values():
                print(diff_text)

    if report.broken_results:
        return 1
    if strict and report.warning_results:
        return 1
    return 0


def _detect_executable_path(target_override: Optional[Path] = None) -> Optional[Path]:
    """Return the path of the running zipapp executable, if applicable."""
    if target_override is not None:
        return target_override.expanduser().resolve()

    argv0 = Path(sys.argv[0]).expanduser()
    if argv0.is_file():
        resolved = argv0.resolve()
        # Verify it looks like a standalone chyg script/zipapp rather than pytest/python
        try:
            head = resolved.read_bytes()[:64]
            if head.startswith(b"#!") and resolved.name != "__main__.py":
                return resolved
        except OSError:
            pass
    return None


def self_update(
    *,
    url: Optional[str] = None,
    target: Optional[Path] = None,
) -> int:
    """Download the latest `chyg` executable and atomically replace the running binary."""
    download_url = url or os.environ.get("CHYG_UPDATE_URL") or DEFAULT_UPDATE_URL
    dest = _detect_executable_path(target)
    if dest is None:
        print(
            "Unable to locate a standalone `chyg` executable to replace. "
            "Pass `--target /path/to/chyg` when running from source.",
            file=sys.stderr,
        )
        return 1

    if not download_url.startswith("https://"):
        print(
            "Update aborted: download URL must use https://.",
            file=sys.stderr,
        )
        return 1

    print(f"Downloading latest chyg from {download_url} ...")
    req = urllib.request.Request(
        download_url,
        headers={"User-Agent": f"chyg/{__version__}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        return 1

    if not payload.startswith(b"#!/usr/bin/env python3"):
        print(
            "Update aborted: downloaded file does not start with expected Python shebang.",
            file=sys.stderr,
        )
        return 1

    tmp_path: Optional[Path] = None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(dest.parent),
            prefix=".chyg-update-",
            delete=False,
        ) as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)

        os.chmod(str(tmp_path), 0o755)
        os.replace(str(tmp_path), str(dest))
        tmp_path = None
    except OSError as exc:
        print(f"Failed to replace {dest}: {exc}", file=sys.stderr)
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return 1

    print(f"Updated {dest} successfully.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="chyg",
        description="Context Hygiene CLI for AI Coding Agents on macOS.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"chyg {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")

    audit_parser = subparsers.add_parser(
        "audit",
        help="Run a non-interactive context hygiene audit",
    )
    audit_parser.add_argument(
        "--path",
        default=None,
        help="Target directory to scan (defaults to Git root or current directory)",
    )
    audit_parser.add_argument(
        "--yes",
        action="store_true",
        help="Bypass interactive scope confirmation prompts (for CI)",
    )
    audit_parser.add_argument(
        "--global",
        dest="global_scan",
        action="store_true",
        help="Audit global agent config directories (~/.claude, ~/.cursor, ~/.codex, ~/.config/opencode)",
    )
    audit_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any warnings or errors are found",
    )
    audit_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output machine-readable JSON",
    )
    audit_parser.add_argument(
        "--stale-days",
        type=int,
        default=None,
        help="Override staleness threshold in days (default: 120)",
    )
    audit_parser.add_argument(
        "--fix",
        action="store_true",
        help="Safely strip verified dead-path lines (creates .bak backup and prints diff)",
    )

    update_parser = subparsers.add_parser(
        "update",
        help="Download the latest chyg executable and atomically replace itself",
    )
    update_parser.add_argument(
        "--url",
        default=None,
        help="Override download URL (defaults to CHYG_UPDATE_URL or GitHub raw URL)",
    )
    update_parser.add_argument(
        "--target",
        default=None,
        help="Override target binary path to replace",
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command is None:
        from context_hygiene.tui import run_tui

        return run_tui()

    if args.command == "audit":
        return run_audit(
            path_arg=args.path,
            global_scan=args.global_scan,
            auto_yes=args.yes,
            strict=args.strict,
            as_json=args.as_json,
            stale_days=args.stale_days,
            apply_fix=args.fix,
        )

    if args.command == "update":
        target = Path(args.target) if args.target else None
        return self_update(url=args.url, target=target)

    parser.print_help()
    return 0
