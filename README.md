# `chyg` — Context Hygiene CLI for AI Coding Agents

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/stefanasemota/chyg)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)](https://github.com/stefanasemota/chyg)
[![Python](https://img.shields.io/badge/Python-3.9%2B%20Stdlib%20Only-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Platform](https://img.shields.io/badge/macOS-TCC%20Safe-000000?logo=apple&logoColor=white)](src/context_hygiene/discovery.py)

> Keep AI coding context lean and clean.

## Goal

AI coding agents load instruction files (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.windsurfrules`, `.github/copilot-instructions.md`, `.cursor/rules/*.mdc`, and `**/SKILL.md`) into every session. Over time, these files accumulate token bloat, stale rules, broken file/script references, generic prompt fluff, and formatting rules that duplicate existing linters.

`chyg` is a zero-dependency macOS CLI/TUI built on Python's standard library to discover those files safely (respecting macOS TCC privacy boundaries), audit them deterministically across five hygiene rules, and keep your agent context fast, accurate, and high-signal.

## How to Install

### Option 1: One-Line `curl` Install (Recommended, Zero-Build)

```bash
mkdir -p ~/.local/bin && curl -fsSL https://raw.githubusercontent.com/stefanasemota/chyg/main/chyg -o ~/.local/bin/chyg && chmod +x ~/.local/bin/chyg && ~/.local/bin/chyg --version
```

### Option 2: Convenience Wrapper (`install.sh`)

Automatically creates `~/.local/bin` (or falls back to `/usr/local/bin`), downloads `chyg`, sets `+x`, and checks your `PATH`:

```bash
curl -fsSL https://raw.githubusercontent.com/stefanasemota/chyg/main/install.sh | sh
```

### Install Caveats & `PATH` Setup

1. **Missing `~/.local/bin` directory:** `curl -o ~/.local/bin/chyg` does not create parent folders automatically. Always run `mkdir -p ~/.local/bin` first (included in Option 1 above) or use `install.sh`.
2. **`chyg: command not found` (`PATH` configuration):** If `~/.local/bin` is not yet in your shell `PATH`, add the following line to `~/.zshrc` and reload your terminal (`source ~/.zshrc`):
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

## Usage

### Interactive TUI

Run `chyg` with no arguments to launch the keyboard-driven menu (`↑/↓` navigate, `Enter` select, `Q` quit):

1. **Audit Repo** — Scan the current Git repository's instruction and skill files.
2. **Global Scan** — Audit `~/.claude`, `~/.cursor`, `~/.codex`, and `~/.config/opencode` (with explicit `y/N` confirmation).
3. **Token Analyzer** — Rank discovered context files by estimated token weight (`words * 1.3`).
4. **Workspace Sweep** — Audit a custom dev root (e.g., `~/Developer`) after explicit confirmation.
5. **Self-Update** — Atomically replace `chyg` with the latest release over HTTPS.

### Non-Interactive CLI (CI & Scripts)

```bash
chyg audit                           # Audit current repo (read-only)
chyg audit --strict                  # Exit 1 on warnings or broken paths
chyg audit --json                    # Machine-readable JSON output
chyg audit --global --yes            # Audit global agent configs without prompting
chyg audit --stale-days 90           # Override 120-day staleness threshold
chyg audit --fix                     # Strip verified dead-path lines (writes .bak backup + diff)
chyg update                          # Download latest chyg over HTTPS and atomically replace itself
```

## macOS TCC Privacy Guardrails

- Never walks `$HOME`, `~/Desktop`, `~/Documents`, `~/Downloads`, or `~/Library` unless explicitly confirmed by the user.
- Never follows symlinks pointing outside the confirmed scan root.
- Checks `os.access(path, os.R_OK)` and catches `PermissionError` cleanly.

## Configuration

Copy `.context-hygiene.example.json` to `.context-hygiene.json` in your repo root, or override per-file thresholds using YAML frontmatter:

```markdown
---
max_lines: 220
review_after: 2027-01-01
---
```

## Development

See [dev.md](dev.md) for local development, test execution, and zipapp build instructions.

---

Powered by <a href="https://github.com/stefanasemota/vibe-coding-guardrail">aos Vibe Coding Guardrail</a> | Fuel the Project - Buy me a coffee: <a href="https://buymeacoffee.com/stephanasex">https://buymeacoffee.com/stephanasex</a>
