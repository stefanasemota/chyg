"""Unit tests for terminal report formatting and context-budget remediation hints."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from context_hygiene.auditor import audit_files
from context_hygiene.reporter import format_terminal_report


class TestReporterBloatHints(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_bloat_hint_printed_for_bloated_root_file(self) -> None:
        agents = self.repo / "CLAUDE.md"
        agents.write_text(
            "\n".join(f"Rule line {i}" for i in range(160)) + "\n",
            encoding="utf-8",
        )

        report = audit_files([agents], self.repo)
        output = format_terminal_report(report, use_color=False)

        self.assertIn("[context-budget]", output)
        self.assertIn(
            "↳ Hint: Run /caveman-compress CLAUDE.md in your coding agent to shrink with a .bak backup.",
            output,
        )

    def test_bloat_hint_printed_for_bloated_skill_file(self) -> None:
        skill_dir = self.repo / "skills" / "deploy"
        skill_dir.mkdir(parents=True)
        skill = skill_dir / "SKILL.md"
        skill.write_text(
            "\n".join(f"Step {i}" for i in range(305)) + "\n",
            encoding="utf-8",
        )

        report = audit_files([skill], self.repo)
        output = format_terminal_report(report, use_color=False)

        self.assertIn("[context-budget]", output)
        self.assertIn(
            "↳ Hint: Run /caveman-compress skills/deploy/SKILL.md in your coding agent to shrink with a .bak backup.",
            output,
        )

    def test_bloat_hint_printed_even_when_file_also_has_dead_path(self) -> None:
        agents = self.repo / "AGENTS.md"
        lines = [f"Rule line {i}" for i in range(155)]
        lines.append("See `src/nonexistent_module.py` for details.")
        agents.write_text("\n".join(lines) + "\n", encoding="utf-8")

        report = audit_files([agents], self.repo)
        self.assertEqual(len(report.broken_results), 1)
        output = format_terminal_report(report, use_color=False)

        self.assertIn("❌ Broken Paths", output)
        self.assertIn("[dead-path]", output)
        self.assertIn("[context-budget]", output)
        self.assertIn("/caveman-compress AGENTS.md", output)

    def test_no_bloat_hint_for_lean_or_non_bloat_warnings(self) -> None:
        # Lean file
        lean = self.repo / "CLAUDE.md"
        lean.write_text("# Concise\nKeep it short.\n", encoding="utf-8")

        # Non-bloat warnings: prompt-fluff + staleness + dead-path
        warned = self.repo / "AGENTS.md"
        warned.write_text(
            "# Rules\nAlways write clean code.\nCheck `missing/file.py`.\n",
            encoding="utf-8",
        )
        old_ts = time.time() - (200 * 86400)
        os.utime(str(warned), (old_ts, old_ts))

        report = audit_files([lean, warned], self.repo)
        output = format_terminal_report(report, use_color=False)

        self.assertIn("[prompt-fluff]", output)
        self.assertIn("[staleness]", output)
        self.assertIn("[dead-path]", output)
        self.assertNotIn("/caveman-compress", output)


if __name__ == "__main__":
    unittest.main()
