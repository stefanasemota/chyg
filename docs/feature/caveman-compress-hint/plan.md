# Implementation Plan — `feature/caveman-compress-hint`

## Scope
Add a strictly read-only, zero-telemetry remediation hint to `chyg`'s terminal reporter whenever Rule 1 (`context-budget`) flags a bloated instruction file (`> 150` lines for always-on root files like `CLAUDE.md`/`AGENTS.md`, or `> 300` lines for on-demand `SKILL.md`/`.mdc` files).

### Planned Changes
1. **Terminal Reporter (`src/context_hygiene/reporter.py`)**
   - In `format_terminal_report()`, whenever a finding has `rule_id == "context-budget"` (whether the file is listed under `⚠️ Warnings` or `❌ Broken Paths`), emit a concise hint line directly under that finding:
     ```text
     ↳ Hint: Run `/caveman-compress <relative_path>` in your coding agent to shrink with a .bak backup.
     ```
   - Never emit the hint for lean files or non-bloat findings (`staleness`, `dead-path`, `prompt-fluff`, `linter-overlap`).
   - Strictly read-only: never install, download, or execute any external `caveman` binary or proxy.
2. **Documentation (`README.md`)**
   - Document the read-only `/caveman-compress <filepath>` bloat remediation hint in `README.md`.
3. **Unit Tests (`tests/test_reporter.py`)**
   - Verify the `/caveman-compress <filepath>` hint appears for bloated root files (`> 150` lines) and bloated `SKILL.md` files (`> 300` lines), including when a bloated file also has dead paths.
   - Verify the hint does **not** appear for lean files or non-bloat warnings (e.g. `prompt-fluff`, `staleness`, `dead-path` alone).
4. **ADR & Rebuild (`decision.md`, `chyg`)**
   - Prepend a `[27.11.2026]` ADR entry to `decision.md`.
   - Rebuild `./chyg` via `python3 build.py`.

## Trade-offs & Edge Cases
- Checking `f.rule_id == "context-budget"` in both the `broken_results` and `warning_results` rendering loops ensures a file that is both bloated *and* has a dead path still surfaces the compression hint.
- Respects `use_color=False` / `NO_COLOR` cleanly with zero ANSI escapes.
- Keeps zero external dependencies and Python 3.9+ / 3.11+ compatibility.

## Verification Commands
```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 build.py
./chyg --version
./chyg audit --strict
```
