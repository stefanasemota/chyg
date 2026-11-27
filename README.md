# `chyg` — Context Hygiene CLI for AI Coding Agents

[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/stefanasemota/chyg)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)](https://github.com/stefanasemota/chyg)
[![Python](https://img.shields.io/badge/Python-3.9%2B%20Stdlib%20Only-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Platform](https://img.shields.io/badge/macOS-TCC%20Safe-000000?logo=apple&logoColor=white)](src/context_hygiene/discovery.py)

Zero-dependency macOS CLI/TUI tool to discover and audit AI instruction files (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.windsurfrules`, `.github/copilot-instructions.md`, `.cursor/rules/*.mdc`, `**/SKILL.md`) for token bloat, staleness, dead local paths, prompt fluff, and linter overlap.

## Quickstart (Zero-Build `curl`)

```bash
curl -fsSL https://raw.githubusercontent.com/stefanasemota/chyg/main/chyg -o ~/.local/bin/chyg && chmod +x ~/.local/bin/chyg
```

Or use the optional convenience wrapper:

```bash
curl -fsSL https://raw.githubusercontent.com/stefanasemota/chyg/main/install.sh | sh
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
