"""Unit tests for the deterministic 5-rule context hygiene auditor."""

from __future__ import annotations

import datetime
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from context_hygiene.auditor import (
    AuditConfig,
    audit_file,
    audit_files,
    parse_frontmatter,
    remediate_dead_paths,
)


class TestAuditorRules(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_dead_path_and_script_detection(self) -> None:
        (self.repo / "src").mkdir()
        (self.repo / "src" / "live.py").write_text("x = 1\n", encoding="utf-8")
        (self.repo / "package.json").write_text(
            json.dumps({"scripts": {"build": "tsc", "test": "vitest"}}),
            encoding="utf-8",
        )
        (self.repo / "Makefile").write_text(
            "lint:\n\truff check .\n", encoding="utf-8"
        )

        agents = self.repo / "AGENTS.md"
        agents.write_text(
            "\n".join(
                [
                    "# Project Rules",
                    "See `src/live.py` for the main module.",
                    "See `src/missing_module.py` for the old API.",
                    "Run `npm run build` and `npm run nonexistent` before PRs.",
                    "Run `make lint` or `make ghost_target` locally.",
                    "Ignore URLs like `https://example.com/a/b.py` and `y/N`.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        report = audit_files([agents], self.repo)
        self.assertEqual(len(report.results), 1)
        res = report.results[0]
        self.assertEqual(res.status, "broken")

        dead_details = [
            f.detail for f in res.findings if f.rule_id == "dead-path"
        ]
        self.assertIn("src/missing_module.py", dead_details)
        self.assertIn("npm run nonexistent", dead_details)
        self.assertIn("make ghost_target", dead_details)
        self.assertNotIn("src/live.py", dead_details)
        self.assertNotIn("npm run build", dead_details)
        self.assertNotIn("make lint", dead_details)

    def test_frontmatter_max_lines_and_review_after_overrides(self) -> None:
        # 180 lines exceeds default 150-line always-on limit, but frontmatter sets max_lines: 200.
        # Frontmatter review_after is in the past -> must flag staleness even if file was just modified.
        body_lines = [f"Rule line {i}" for i in range(175)]
        agents = self.repo / "AGENTS.md"
        agents.write_text(
            "---\nmax_lines: 200\nreview_after: 2020-01-01\n---\n"
            + "\n".join(body_lines)
            + "\n",
            encoding="utf-8",
        )

        meta, start_idx = parse_frontmatter(agents.read_text(encoding="utf-8"))
        self.assertEqual(meta["max_lines"], 200)
        self.assertEqual(meta["review_after"], "2020-01-01")
        self.assertEqual(start_idx, 4)

        now_ts = datetime.datetime(
            2026, 11, 27, tzinfo=datetime.timezone.utc
        ).timestamp()
        res = audit_file(agents, self.repo, AuditConfig(), now_ts=now_ts)
        rule_ids = [f.rule_id for f in res.findings]
        self.assertNotIn("context-budget", rule_ids)
        self.assertIn("staleness", rule_ids)

        # Future review_after suppresses staleness even for an old file.
        future_agents = self.repo / "CLAUDE.md"
        future_agents.write_text(
            "---\nreview_after: 2030-01-01\n---\nKeep it lean.\n",
            encoding="utf-8",
        )
        old_time = now_ts - (200 * 86400)
        os.utime(str(future_agents), (old_time, old_time))

        res_future = audit_file(
            future_agents, self.repo, AuditConfig(), now_ts=now_ts
        )
        self.assertNotIn("staleness", [f.rule_id for f in res_future.findings])

    def test_context_budget_thresholds_and_json_config_override(self) -> None:
        skill_dir = self.repo / "skills" / "demo"
        skill_dir.mkdir(parents=True)
        skill = skill_dir / "SKILL.md"
        skill.write_text(
            "\n".join(f"Step {i}" for i in range(200)) + "\n", encoding="utf-8"
        )

        # 200 lines is under 300-line skill limit -> lean.
        report = audit_files([skill], self.repo)
        self.assertEqual(report.results[0].status, "lean")

        # Lower skill_max_lines via .context-hygiene.json -> triggers warning.
        (self.repo / ".context-hygiene.json").write_text(
            json.dumps({"skill_max_lines": 100}), encoding="utf-8"
        )
        report_strict = audit_files([skill], self.repo)
        self.assertEqual(report_strict.results[0].status, "warning")
        self.assertIn(
            "context-budget",
            [f.rule_id for f in report_strict.results[0].findings],
        )

    def test_staleness_via_mtime_threshold(self) -> None:
        agents = self.repo / "AGENTS.md"
        agents.write_text("# Fresh rules\n", encoding="utf-8")
        now_ts = time.time()
        old_ts = now_ts - (150 * 86400)
        os.utime(str(agents), (old_ts, old_ts))

        res = audit_file(agents, self.repo, AuditConfig(stale_days=120), now_ts=now_ts)
        self.assertIn("staleness", [f.rule_id for f in res.findings])

    def test_prompt_fluff_detection(self) -> None:
        agents = self.repo / "AGENTS.md"
        agents.write_text(
            "# Guidelines\nAlways write clean code and do not hallucinate.\n",
            encoding="utf-8",
        )
        res = audit_file(agents, self.repo, AuditConfig())
        fluff_findings = [f for f in res.findings if f.rule_id == "prompt-fluff"]
        self.assertEqual(len(fluff_findings), 1)
        self.assertEqual(fluff_findings[0].line, 2)

    def test_linter_overlap_only_when_linter_config_present(self) -> None:
        agents = self.repo / "AGENTS.md"
        agents.write_text(
            "# Style\nAlways use single quotes and no semicolons.\n",
            encoding="utf-8",
        )

        # Without a linter config, no linter-overlap warning.
        res_no_linter = audit_file(agents, self.repo, AuditConfig())
        self.assertNotIn(
            "linter-overlap", [f.rule_id for f in res_no_linter.findings]
        )

        # Add .prettierrc -> triggers linter-overlap warning.
        (self.repo / ".prettierrc").write_text("{}\n", encoding="utf-8")
        res_with_linter = audit_file(agents, self.repo, AuditConfig())
        overlap = [
            f for f in res_with_linter.findings if f.rule_id == "linter-overlap"
        ]
        self.assertEqual(len(overlap), 1)
        self.assertIn("Prettier", overlap[0].message)

    def test_safe_remediation_writes_backup_and_strips_dead_lines(self) -> None:
        (self.repo / "keep.py").write_text("pass\n", encoding="utf-8")
        agents = self.repo / "AGENTS.md"
        original = (
            "# Rules\n"
            "Keep `keep.py` updated.\n"
            "Remove reference to `ghost/deleted.py`.\n"
        )
        agents.write_text(original, encoding="utf-8")

        report = audit_files([agents], self.repo)
        diffs = remediate_dead_paths(report, write_backup=True)

        self.assertIn(agents, diffs)
        self.assertIn("-Remove reference to `ghost/deleted.py`.", diffs[agents])
        backup = agents.with_name("AGENTS.md.bak")
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.read_text(encoding="utf-8"), original)
        self.assertNotIn("ghost/deleted.py", agents.read_text(encoding="utf-8"))
        self.assertIn("keep.py", agents.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
