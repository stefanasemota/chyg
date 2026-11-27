Here is the updated `INITIATIVE.md` tailored for a **direct, zero-build single-file `curl` installation** (making `install.sh` optional and keeping a committed `chyg` executable right in the repo so `curl -fsSL ... -o ~/.local/bin/chyg && chmod +x ~/.local/bin/chyg` works out of the box).

Save the content below directly as **`INITIATIVE.md`**:

```markdown
# INITIATIVE.md — `chyg` (Context Hygiene CLI for macOS)

## 1. Objective
Build `chyg` (`context-hygiene`), a super-lightweight, zero-dependency macOS CLI/TUI tool inspired by `tw93/mole`. Distributed as a single committed executable script (`chyg`) in the repository root so users can install it with a single `curl` command (with an optional `install.sh` convenience wrapper) and sub-50ms startup. `chyg` discovers AI instruction files (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `**/SKILL.md`), safely respects macOS TCC privacy boundaries, and provides an interactive terminal dashboard to audit token bloat, dead paths, stale rules, and linter overlap.

---

## 2. Installation & Distribution Model (Zero-Build `curl`)

Because the entire tool uses the Python 3.11+ standard library, it must be runnable both as a modular package (`src/context_hygiene/`) during development and as a single self-contained executable (`chyg` in the repo root) built via `build.py` (standard library `zipapp`).

- **Primary One-Line `curl` Install (No clone or build step required):**
  ```bash
  curl -fsSL [https://raw.githubusercontent.com/](https://raw.githubusercontent.com/)<OWNER>/context-hygiene/main/chyg -o ~/.local/bin/chyg && chmod +x ~/.local/bin/chyg

```

* **Optional Convenience Wrapper (`install.sh`):**
Detects `~/.local/bin` or `/usr/local/bin`, downloads `chyg`, applies `chmod +x`, and verifies `PATH`.
* **Self-Update (`chyg update`):**
Fetches the latest raw `chyg` binary directly from GitHub and atomically replaces the running executable.

---

## 3. UX & Execution Lifecycle (Mole-Inspired TUI)

Running `chyg` with no arguments launches a clean, fast, keyboard-driven TUI (`↑/↓` navigate, `Enter` select, `Q` quit):

```text
   ___ _  _ _   _  ___ 
  / __| || | | | |/ __|
 | (__| __ | |_| | (_ |
  \___|_||_|\__, |\___|  Context Hygiene for AI Coding Agents
            |___/      

  > 1. Audit Repo       Scan current project instructions & skills
    2. Global Scan      Audit ~/.claude, ~/.cursor, ~/.codex, ~/.config/opencode
    3. Token Analyzer   Rank context files by token weight & bloat
    4. Workspace Sweep  Select a custom dev root (e.g., ~/Developer)
    5. Self-Update      Update chyg to the latest release

  ↑↓ | Enter | Q Quit

```

### Phase 1: macOS TCC-Safe Discovery

1. **Environment Check:** Verify macOS (`Darwin`), detect Git root (`git rev-parse --show-toplevel`), and identify standard agent config paths (`~/.claude`, `~/.cursor`, `~/.codex`, `~/.config/opencode`).
2. **Strict TCC Guardrails:**
* Never walk `$HOME` (`~`), `~/Desktop`, `~/Documents`, `~/Downloads`, or `~/Library` unless explicitly selected by the user.
* Do not follow symlinks pointing outside the confirmed scan root.
* Catch `PermissionError` and check `os.access(path, os.R_OK)` before opening any file or directory.



### Phase 2: Explicit Scope Confirmation

Before scanning outside the current Git repository (e.g., Options 2 or 4), display the exact target paths and require explicit confirmation (`y/N`), bypassable via `--yes` for CI.

### Phase 3: Model-Agnostic Hygiene Rules

Audit discovered files (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.windsurfrules`, `.github/copilot-instructions.md`, `.cursor/rules/*.mdc`, `**/SKILL.md`) against five deterministic rules:

1. **Context Budget (Token Bloat):**
* Always-on root files (`CLAUDE.md`, `AGENTS.md`, `.cursorrules`): Warn if `> 150 lines` (overridable via YAML frontmatter `max_lines:` or `.context-hygiene.json`).
* On-demand skills (`SKILL.md`, `.mdc`): Warn if `> 300 lines`.


2. **Staleness / Capability Creep:**
* Check `git log -1 --format=%ct` (or `mtime` if untracked).
* Flag files untouched for `> 120 days` (or past frontmatter `review_after: YYYY-MM-DD`) to prompt an ablation check on newer models.


3. **Dead Local References:**
* Extract backticked relative paths (e.g., ``src/api/client.ts``) and script commands (`npm run <script>`, `make <target>`).
* Verify paths exist relative to repo root and scripts exist in `package.json`, `Makefile`, or `pyproject.toml`.


4. **Low-Signal Prompt Fluff:**
* Flag generic directives modern frontier models handle natively (e.g., *"write clean code"*, *"do not hallucinate"*, *"handle all edge cases"*, *"think step by step"*).


5. **Deterministic Linter Overlap:**
* Detect project formatters/linters (`.prettierrc*`, `biome.json`, `.eslintrc*`, `ruff.toml`, `pyproject.toml`, `.swiftformat`).
* Flag prose formatting rules (indentation, quotes, semicolons, line length) that duplicate existing tool configs.



### Phase 4: Actionable Report & Safe Remediation

* Display grouped results (`✅ Lean`, `⚠️ Warnings`, `❌ Broken Paths`) with estimated token footprint (`words * 1.3`).
* Default mode is strictly read-only. If `--fix` is explicitly passed (or triggered via interactive confirmation), safely strip verified dead path lines while writing a `.bak` backup or printing a unified diff.

---

## 4. Repository Structure & Packaging

```text
context-hygiene/
├── INITIATIVE.md                 # This specification
├── README.md                     # One-line curl quickstart, TUI guide, macOS TCC notes
├── chyg                          # Pre-built single-file zipapp executable (chmod +x) for direct curl
├── build.py                      # Bundles src/context_hygiene into ./chyg via stdlib zipapp
├── install.sh                    # Optional convenience installer wrapping the curl command
├── pyproject.toml                # Zero-dependency standard-library config
├── .context-hygiene.example.json # Optional per-repo threshold & ignore overrides
├── src/
│   └── context_hygiene/
│       ├── __init__.py
│       ├── __main__.py           # Entrypoint for zipapp / CLI execution
│       ├── tui.py                # Zero-dependency ANSI/termios arrow-key menu (Mole-style)
│       ├── cli.py                # Flag parser (--yes, --global, --strict, --json, --stale-days)
│       ├── discovery.py          # macOS TCC-safe discovery & symlink boundary checks
│       ├── auditor.py            # Deterministic 5-rule hygiene engine
│       └── reporter.py           # Terminal summary & JSON output formatter
└── tests/
    ├── test_discovery.py
    └── test_auditor.py

```

---

## 5. Technical Constraints & CLI Flags

* **Zero External Dependencies:** Python 3.11+ standard library only (`pathlib`, `re`, `subprocess`, `argparse`, `json`, `os`, `platform`, `time`, `termios`, `tty`, `zipapp`, `urllib.request`, `unittest`).
* **Single-File Distribution:** `build.py` bundles `src/context_hygiene` using Python's built-in `zipapp` module with a `#!/usr/bin/env python3` shebang into `./chyg` (`chmod +x`), so users can download and run `./chyg` immediately via `curl` without cloning or installing anything.
* **Supported Flags (Bypass TUI for CI/Scripts):**
* `chyg` (no flags): Launch interactive Mole-style TUI
* `chyg audit [--yes] [--global] [--strict] [--json] [--stale-days <int>] [--fix]`: Non-interactive audit mode
* `chyg update`: Download the latest `chyg` executable from GitHub and atomically replace itself



---

## 6. Initial Build Instructions (Prompt for Coding Agent)

> Read `INITIATIVE.md` completely. Scaffold the repository structure in Section 4 using Python 3.11+ standard library modules only. Implement the interactive ANSI/termios TUI menu in `tui.py`, direct CLI flags and atomic self-update (`chyg update`) in `cli.py`, macOS TCC-safe path discovery (including symlink escape prevention) in `discovery.py`, all five deterministic audit rules in `auditor.py`, `build.py` to compile the single-file `zipapp` executable `./chyg`, and an optional `install.sh` wrapper. Write unit tests in `tests/` covering dead-path detection, frontmatter overrides, symlink guardrails, and macOS protected-directory skipping, run the test suite, and build `./chyg` to verify it executes standalone.

```

```