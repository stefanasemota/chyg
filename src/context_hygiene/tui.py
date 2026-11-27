"""Zero-dependency ANSI/termios interactive TUI menu (Mole-style)."""

from __future__ import annotations

import os
import sys
import termios
import tty
from pathlib import Path
from typing import Sequence

from context_hygiene.auditor import audit_files, remediate_dead_paths
from context_hygiene.cli import confirm_scope, self_update
from context_hygiene.discovery import (
    detect_git_root,
    discover_instruction_files,
    is_macos,
    is_protected_path,
    standard_agent_config_paths,
)
from context_hygiene.reporter import format_terminal_report, format_token_ranking

BANNER = r"""   ___ _  _ _   _  ___ 
  / __| || | | | |/ __|
 | (__| __ | |_| | (_ |
  \___|_||_|\__, |\___|  Context Hygiene for AI Coding Agents
            |___/      """

MENU_ITEMS: tuple[tuple[str, str], ...] = (
    ("1. Audit Repo", "Scan current project instructions & skills"),
    ("2. Global Scan", "Audit ~/.claude, ~/.cursor, ~/.codex, ~/.config/opencode"),
    ("3. Token Analyzer", "Rank context files by token weight & bloat"),
    ("4. Workspace Sweep", "Select a custom dev root (e.g., ~/Developer)"),
    ("5. Self-Update", "Update chyg to the latest release"),
)

CLEAR_SCREEN = "\x1b[2J\x1b[H"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
CYAN = "\x1b[36m"
RESET = "\x1b[0m"


def render_menu(selected_index: int, *, use_color: bool = True) -> str:
    """Render the Mole-inspired TUI menu string."""
    lines: list[str] = []
    if use_color:
        lines.append(f"{CYAN}{BANNER}{RESET}")
    else:
        lines.append(BANNER)
    lines.append("")

    for idx, (label, desc) in enumerate(MENU_ITEMS):
        if idx == selected_index:
            prefix = f"{BOLD}{CYAN}> {label:<18}{RESET}" if use_color else f"> {label:<18}"
            lines.append(f"  {prefix} {desc}")
        else:
            dim_desc = f"{DIM}{desc}{RESET}" if use_color else desc
            lines.append(f"    {label:<18} {dim_desc}")

    lines.append("")
    footer = "  ↑↓ | Enter | Q Quit"
    lines.append(f"{DIM}{footer}{RESET}" if use_color else footer)
    return "\n".join(lines)


def read_key(fd: int) -> str:
    """Read a single keystroke or ANSI arrow sequence in raw terminal mode."""
    ch = os.read(fd, 1)
    if not ch:
        return "quit"
    if ch in (b"q", b"Q", b"\x03", b"\x04"):
        return "quit"
    if ch in (b"\r", b"\n"):
        return "enter"
    if ch in (b"k", b"K"):
        return "up"
    if ch in (b"j", b"J"):
        return "down"
    if ch in (b"1", b"2", b"3", b"4", b"5"):
        return ch.decode("ascii")
    if ch == b"\x1b":
        seq = os.read(fd, 2)
        if seq == b"[A":
            return "up"
        if seq == b"[B":
            return "down"
        return "esc"
    return "other"


def _pause_for_return() -> None:
    print("")
    try:
        input("Press Enter to return to menu...")
    except (EOFError, KeyboardInterrupt):
        pass


def _maybe_offer_fix(report_obj) -> None:
    if not report_obj.broken_results:
        return
    try:
        answer = input(
            "\nBroken path references detected. Strip dead-path lines with .bak backup? [y/N]: "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if answer in ("y", "yes"):
        diffs = remediate_dead_paths(report_obj, write_backup=True)
        print(f"\nRemediated {len(diffs)} file(s):")
        for diff_text in diffs.values():
            print(diff_text)


def _action_audit_repo(use_color: bool) -> None:
    root = detect_git_root() or Path.cwd()
    discovery = discover_instruction_files([root])
    report = audit_files(
        discovery.files,
        root,
        skipped_protected=discovery.skipped_protected,
        skipped_symlinks=discovery.skipped_symlinks,
        skipped_unreadable=discovery.skipped_unreadable,
    )
    print(format_terminal_report(report, use_color=use_color))
    _maybe_offer_fix(report)


def _action_global_scan(use_color: bool) -> None:
    targets = standard_agent_config_paths()
    if not confirm_scope(targets, auto_yes=False):
        print("Global scan cancelled.")
        return
    existing = [p for p in targets if p.exists()]
    discovery = discover_instruction_files(existing)
    report = audit_files(
        discovery.files,
        Path.home(),
        skipped_protected=discovery.skipped_protected,
        skipped_symlinks=discovery.skipped_symlinks,
        skipped_unreadable=discovery.skipped_unreadable,
    )
    print(format_terminal_report(report, use_color=use_color))
    _maybe_offer_fix(report)


def _action_token_analyzer(use_color: bool) -> None:
    root = detect_git_root() or Path.cwd()
    discovery = discover_instruction_files([root])
    report = audit_files(
        discovery.files,
        root,
        skipped_protected=discovery.skipped_protected,
        skipped_symlinks=discovery.skipped_symlinks,
        skipped_unreadable=discovery.skipped_unreadable,
    )
    print(format_token_ranking(report, use_color=use_color))


def _action_workspace_sweep(use_color: bool) -> None:
    default_root = Path.home() / "Developer"
    try:
        raw = input(
            f"Enter dev root to sweep [{default_root}]: "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nWorkspace sweep cancelled.")
        return
    target = Path(raw).expanduser().resolve() if raw else default_root
    if not target.exists():
        print(f"Directory does not exist: {target}")
        return

    protected = is_protected_path(target)
    if protected:
        print(f"Warning: {target} is a macOS TCC-protected location.")
    if not confirm_scope([target], auto_yes=False):
        print("Workspace sweep cancelled.")
        return

    discovery = discover_instruction_files([target], allow_protected=protected)
    report = audit_files(
        discovery.files,
        target,
        skipped_protected=discovery.skipped_protected,
        skipped_symlinks=discovery.skipped_symlinks,
        skipped_unreadable=discovery.skipped_unreadable,
    )
    print(format_terminal_report(report, use_color=use_color))
    _maybe_offer_fix(report)


def _execute_selection(index: int, use_color: bool) -> None:
    sys.stdout.write(CLEAR_SCREEN)
    sys.stdout.flush()
    if index == 0:
        _action_audit_repo(use_color)
    elif index == 1:
        _action_global_scan(use_color)
    elif index == 2:
        _action_token_analyzer(use_color)
    elif index == 3:
        _action_workspace_sweep(use_color)
    elif index == 4:
        self_update()
    _pause_for_return()


def run_tui() -> int:
    """Launch the interactive ANSI/termios menu."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("chyg interactive TUI requires a TTY. Use `chyg audit` for non-interactive mode.")
        return 1

    use_color = not os.environ.get("NO_COLOR")
    if not is_macos():
        # Informative note only; still works on POSIX terminals.
        pass

    selected = 0
    fd = sys.stdin.fileno()
    old_settings: Sequence[object] = termios.tcgetattr(fd)

    try:
        while True:
            sys.stdout.write(CLEAR_SCREEN + HIDE_CURSOR)
            sys.stdout.write(render_menu(selected, use_color=use_color) + "\n")
            sys.stdout.flush()

            tty.setraw(fd)
            try:
                key = read_key(fd)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

            if key == "quit":
                break
            if key == "up":
                selected = (selected - 1) % len(MENU_ITEMS)
            elif key == "down":
                selected = (selected + 1) % len(MENU_ITEMS)
            elif key in ("1", "2", "3", "4", "5"):
                selected = int(key) - 1
                sys.stdout.write(SHOW_CURSOR)
                sys.stdout.flush()
                _execute_selection(selected, use_color)
            elif key == "enter":
                sys.stdout.write(SHOW_CURSOR)
                sys.stdout.flush()
                _execute_selection(selected, use_color)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()

    return 0
