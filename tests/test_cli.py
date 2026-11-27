"""Unit tests for CLI flags, JSON output, and atomic self-update."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from context_hygiene import CATCHPHRASE, REPO_URL, __version__
from context_hygiene.cli import main, self_update
from context_hygiene.tui import render_menu


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class TestCLIAndSelfUpdate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_audit_json_and_strict_exit_codes(self) -> None:
        repo = self.base / "repo"
        repo.mkdir()
        agents = repo / "AGENTS.md"
        agents.write_text("# Clean\nAlways write clean code.\n", encoding="utf-8")

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["audit", "--path", str(repo), "--yes", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["summary"]["warnings"], 1)

        buf_strict = io.StringIO()
        with redirect_stdout(buf_strict):
            strict_code = main(
                ["audit", "--path", str(repo), "--yes", "--strict", "--json"]
            )
        self.assertEqual(strict_code, 1)

    def test_self_update_rejects_non_https_url(self) -> None:
        target = self.base / "chyg"
        target.write_bytes(b"#!/usr/bin/env python3\nold\n")

        err = io.StringIO()
        with redirect_stderr(err):
            code = self_update(url="http://example.com/chyg", target=target)
        self.assertEqual(code, 1)
        self.assertIn("https://", err.getvalue())

    def test_self_update_atomically_replaces_executable(self) -> None:
        target = self.base / "chyg"
        target.write_bytes(b"#!/usr/bin/env python3\nold\n")
        new_payload = b"#!/usr/bin/env python3\nprint('updated')\n"

        with mock.patch(
            "urllib.request.urlopen", return_value=_FakeResponse(new_payload)
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                code = self_update(
                    url="https://raw.githubusercontent.com/stefanasemota/chyg/main/chyg",
                    target=target,
                )

        self.assertEqual(code, 0)
        self.assertEqual(target.read_bytes(), new_payload)
        self.assertTrue(os.access(str(target), os.X_OK))

    def test_tui_render_menu_displays_url_catchphrase_and_version(self) -> None:
        plain = render_menu(0, use_color=False)
        self.assertIn(REPO_URL, plain)
        self.assertIn(CATCHPHRASE, plain)
        self.assertIn(f"v{__version__}", plain)
        self.assertIn("chyg update", plain)
        self.assertIn("➤ 1. Audit Repo", plain)
        self.assertNotIn("\x1b[", plain)


if __name__ == "__main__":
    unittest.main()
