"""Terminal summary, token analyzer, and JSON output formatters."""

from __future__ import annotations

import json
from typing import Any

from context_hygiene.auditor import AuditReport, FileAuditResult

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
CYAN = "\x1b[36m"


def _c(text: str, code: str, use_color: bool) -> str:
    return f"{code}{text}{RESET}" if use_color else text


def _format_file_meta(res: FileAuditResult) -> str:
    age_str = f"{res.age_days}d" if res.age_days is not None else "n/a"
    return (
        f"{res.line_count} lines | ~{res.estimated_tokens:,} tokens | "
        f"age {age_str} ({res.last_modified_source})"
    )


def format_terminal_report(report: AuditReport, *, use_color: bool = True) -> str:
    """Format an `AuditReport` into grouped terminal sections."""
    lines: list[str] = []
    lines.append(
        _c(f"chyg audit — {report.root}", BOLD + CYAN, use_color)
    )
    lines.append(
        _c(
            f"Scanned {len(report.results)} file(s) | "
            f"Total footprint: ~{report.total_tokens:,} tokens | "
            f"✅ {len(report.lean_results)} Lean  "
            f"⚠️ {len(report.warning_results)} Warnings  "
            f"❌ {len(report.broken_results)} Broken Paths",
            DIM,
            use_color,
        )
    )

    if not report.results:
        lines.append("")
        lines.append("No AI instruction or skill files discovered.")
    else:
        if report.broken_results:
            lines.append("")
            lines.append(_c("❌ Broken Paths", BOLD + RED, use_color))
            for res in report.broken_results:
                lines.append(
                    f"  {_c(res.relative_path, BOLD, use_color)} "
                    f"{_c('(' + _format_file_meta(res) + ')', DIM, use_color)}"
                )
                for f in res.findings:
                    loc = f"L{f.line}: " if f.line is not None else ""
                    color = RED if f.severity == "error" else YELLOW
                    lines.append(
                        f"    {_c('•', color, use_color)} [{f.rule_id}] {loc}{f.message}"
                    )

        if report.warning_results:
            lines.append("")
            lines.append(_c("⚠️ Warnings", BOLD + YELLOW, use_color))
            for res in report.warning_results:
                lines.append(
                    f"  {_c(res.relative_path, BOLD, use_color)} "
                    f"{_c('(' + _format_file_meta(res) + ')', DIM, use_color)}"
                )
                for f in res.findings:
                    loc = f"L{f.line}: " if f.line is not None else ""
                    lines.append(
                        f"    {_c('•', YELLOW, use_color)} [{f.rule_id}] {loc}{f.message}"
                    )

        if report.lean_results:
            lines.append("")
            lines.append(_c("✅ Lean", BOLD + GREEN, use_color))
            for res in report.lean_results:
                lines.append(
                    f"  {res.relative_path} "
                    f"{_c('(' + _format_file_meta(res) + ')', DIM, use_color)}"
                )

    if report.skipped_protected or report.skipped_symlinks or report.skipped_unreadable:
        lines.append("")
        lines.append(_c("Guardrail Skips", DIM, use_color))
        if report.skipped_protected:
            lines.append(
                f"  Protected TCC dirs skipped: {len(report.skipped_protected)}"
            )
        if report.skipped_symlinks:
            lines.append(
                f"  Symlinks skipped (boundary/cycle): {len(report.skipped_symlinks)}"
            )
        if report.skipped_unreadable:
            lines.append(
                f"  Unreadable paths skipped: {len(report.skipped_unreadable)}"
            )

    return "\n".join(lines)


def format_token_ranking(report: AuditReport, *, use_color: bool = True) -> str:
    """Rank discovered instruction files by estimated token weight."""
    lines: list[str] = []
    lines.append(
        _c(f"Token Analyzer — {report.root}", BOLD + CYAN, use_color)
    )
    if not report.results:
        lines.append("No AI instruction or skill files discovered.")
        return "\n".join(lines)

    ranked = sorted(
        report.results, key=lambda r: r.estimated_tokens, reverse=True
    )
    total = max(1, report.total_tokens)
    max_tokens = max(1, ranked[0].estimated_tokens)

    lines.append(
        _c(
            f"Total estimated footprint: ~{report.total_tokens:,} tokens across {len(ranked)} file(s)",
            DIM,
            use_color,
        )
    )
    lines.append("")

    for idx, res in enumerate(ranked, start=1):
        pct = (res.estimated_tokens / total) * 100.0
        bar_len = max(1, int(round((res.estimated_tokens / max_tokens) * 20)))
        bar = "█" * bar_len + "░" * (20 - bar_len)
        status_icon = (
            "❌" if res.status == "broken" else ("⚠️" if res.status == "warning" else "✅")
        )
        lines.append(
            f"  {idx:>2}. {status_icon} {res.estimated_tokens:>6,} tok ({pct:>5.1f}%) "
            f"{_c(bar, CYAN, use_color)}  {res.relative_path} "
            f"{_c(f'[{res.line_count}L, {res.category}]', DIM, use_color)}"
        )

    return "\n".join(lines)


def report_to_dict(report: AuditReport) -> dict[str, Any]:
    """Convert an `AuditReport` to a JSON-serializable dictionary."""
    return {
        "root": str(report.root),
        "summary": {
            "total_files": len(report.results),
            "total_estimated_tokens": report.total_tokens,
            "lean": len(report.lean_results),
            "warnings": len(report.warning_results),
            "broken": len(report.broken_results),
        },
        "files": [
            {
                "path": str(res.path),
                "relative_path": res.relative_path,
                "category": res.category,
                "status": res.status,
                "line_count": res.line_count,
                "word_count": res.word_count,
                "estimated_tokens": res.estimated_tokens,
                "age_days": res.age_days,
                "last_modified_source": res.last_modified_source,
                "findings": [
                    {
                        "rule_id": f.rule_id,
                        "severity": f.severity,
                        "message": f.message,
                        "line": f.line,
                        "detail": f.detail,
                        "fixable": f.fixable,
                    }
                    for f in res.findings
                ],
            }
            for res in report.results
        ],
        "skipped": {
            "protected": [str(p) for p in report.skipped_protected],
            "symlinks": [str(p) for p in report.skipped_symlinks],
            "unreadable": [str(p) for p in report.skipped_unreadable],
        },
    }


def format_json_report(report: AuditReport) -> str:
    """Serialize an `AuditReport` as pretty-printed JSON."""
    return json.dumps(report_to_dict(report), indent=2)
