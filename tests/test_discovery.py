"""Unit tests for macOS TCC-safe discovery and symlink guardrails."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from context_hygiene.discovery import (
    discover_instruction_files,
    is_protected_path,
    is_within_root,
)


class TestDiscoveryGuardrails(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_discovers_all_supported_instruction_patterns(self) -> None:
        repo = self.base / "repo"
        (repo / ".github").mkdir(parents=True)
        (repo / ".cursor" / "rules").mkdir(parents=True)
        (repo / "skills" / "deploy").mkdir(parents=True)
        (repo / "node_modules" / "pkg").mkdir(parents=True)

        expected = [
            repo / "AGENTS.md",
            repo / "CLAUDE.md",
            repo / ".cursorrules",
            repo / ".windsurfrules",
            repo / ".github" / "copilot-instructions.md",
            repo / ".cursor" / "rules" / "style.mdc",
            repo / "skills" / "deploy" / "SKILL.md",
        ]
        for p in expected:
            p.write_text("# instruction\n", encoding="utf-8")

        # Should be ignored
        (repo / "README.md").write_text("# readme\n", encoding="utf-8")
        (repo / "node_modules" / "pkg" / "AGENTS.md").write_text(
            "# ignored\n", encoding="utf-8"
        )

        result = discover_instruction_files([repo], home=self.base / "fake_home")
        self.assertEqual(sorted(result.files), sorted(expected))

    def test_skips_macos_protected_directories_by_default(self) -> None:
        fake_home = self.base / "home"
        for sub in ("Desktop", "Documents", "Downloads", "Library", ".claude"):
            d = fake_home / sub
            d.mkdir(parents=True)
            (d / "AGENTS.md").write_text("# test\n", encoding="utf-8")
        (fake_home / "AGENTS.md").write_text("# home root\n", encoding="utf-8")

        # Directly passing $HOME or TCC-protected dirs without allow_protected must skip them.
        protected_roots = [
            fake_home,
            fake_home / "Desktop",
            fake_home / "Documents",
            fake_home / "Downloads",
            fake_home / "Library",
        ]
        result = discover_instruction_files(
            protected_roots, home=fake_home, allow_protected=False
        )
        self.assertEqual(result.files, [])
        self.assertEqual(len(result.skipped_protected), len(protected_roots))

        # Standard agent config path (~/.claude) is NOT protected and must be scanned.
        agent_res = discover_instruction_files(
            [fake_home / ".claude"], home=fake_home, allow_protected=False
        )
        self.assertEqual(agent_res.files, [fake_home / ".claude" / "AGENTS.md"])
        self.assertEqual(agent_res.skipped_protected, [])

    def test_allows_protected_directory_when_explicitly_selected(self) -> None:
        fake_home = self.base / "home"
        docs = fake_home / "Documents"
        docs.mkdir(parents=True)
        agents = docs / "AGENTS.md"
        agents.write_text("# explicit docs\n", encoding="utf-8")

        self.assertTrue(is_protected_path(docs, home=fake_home))
        self.assertFalse(
            is_protected_path(docs, home=fake_home, explicit_roots=[docs])
        )

        result = discover_instruction_files(
            [docs], home=fake_home, allow_protected=True
        )
        self.assertEqual(result.files, [agents])
        self.assertEqual(result.skipped_protected, [])

    def test_blocks_symlink_escape_for_files_and_directories(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        secret_file = outside / "AGENTS.md"
        secret_file.write_text("# outside secret\n", encoding="utf-8")

        repo = self.base / "repo"
        repo.mkdir()
        local_agents = repo / "CLAUDE.md"
        local_agents.write_text("# safe local\n", encoding="utf-8")

        # Symlinked file pointing outside scan root
        escaping_file_link = repo / "AGENTS.md"
        os.symlink(str(secret_file), str(escaping_file_link))

        # Symlinked directory pointing outside scan root
        escaping_dir_link = repo / "external_dir"
        os.symlink(str(outside), str(escaping_dir_link))

        self.assertFalse(is_within_root(escaping_file_link, repo))
        self.assertTrue(is_within_root(local_agents, repo))

        result = discover_instruction_files([repo], home=self.base / "fake_home")
        self.assertEqual(result.files, [local_agents])
        self.assertIn(escaping_file_link, result.skipped_symlinks)
        self.assertIn(escaping_dir_link, result.skipped_symlinks)

    def test_handles_unreadable_file_gracefully(self) -> None:
        repo = self.base / "repo"
        repo.mkdir()
        locked = repo / "AGENTS.md"
        locked.write_text("# locked\n", encoding="utf-8")
        os.chmod(str(locked), 0)
        try:
            # Skip assertion if running as root where chmod 0 is still readable.
            if not os.access(str(locked), os.R_OK):
                result = discover_instruction_files(
                    [repo], home=self.base / "fake_home"
                )
                self.assertEqual(result.files, [])
                self.assertIn(locked, result.skipped_unreadable)
        finally:
            os.chmod(str(locked), stat.S_IRUSR | stat.S_IWUSR)


if __name__ == "__main__":
    unittest.main()
