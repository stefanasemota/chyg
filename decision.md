# Architectural Decision Ledger (`decision.md`)

Reverse-chronological record of architectural decisions (newest at top).

## [27.11.2026] — Release v1.0.0 with Mole-Style TUI Header & Install Guide
- **Origin:** Post-launch UX & documentation optimization (`feature/tui-header-readme-v1`).
- **Context:** The initial TUI header lacked the repository URL, product catchphrase, and visible version indicator, and `README.md` needed an explicit Goal section plus installation caveats (`mkdir -p ~/.local/bin` and `$PATH`).
- **Decision:** Bump `chyg` to `v1.0.0`, update `tui.py` `render_menu()` to display the GitHub URL, catchphrase, and current version line analogously to `tw93/mole`, and expand `README.md` with Goal and How to Install sections.
- **Impact:** Gives users immediate version visibility and update guidance inside the TUI and prevents first-run `curl`/`PATH` friction.

## [27.11.2026] — Align Scaffolding with Guardrail v2.0 & Harden Self-Update
- **Origin:** Pre-publish project audit and security review.
- **Context:** Before publishing `stefanasemota/chyg`, the repository needed guardrail v2.0 compliance (lean Python-native docs, zero legacy Node/multi-vendor plumbing) and strict URL scheme validation in `self_update()`.
- **Decision:** Add `dev.md`, `decision.md`, `LICENSE`, concise `AGENTS.md`, security exclusions in `.gitignore`, enforce `https://` in `self_update()`, point default update/install URLs to `stefanasemota/chyg`, and add CLI unit tests.
- **Impact:** Prevents `file://`/`http://` URL injection during self-update, keeps the repository zero-dependency and self-auditable (`./chyg audit --strict` passes), and satisfies guardrail v2.0 ADR checks.

## [27.11.2026] — Zero-Dependency Python Stdlib Zipapp Architecture
- **Origin:** `INITIATIVE.md` specification.
- **Context:** Users need sub-50ms startup and single-command `curl` installation on macOS without installing Node.js, `pip`, or virtual environments.
- **Decision:** Implement `src/context_hygiene/` using Python standard library modules only (`from __future__ import annotations` + optional `tomllib` fallback for macOS's default Python 3.9+) and compile to a committed single-file `./chyg` zipapp via `build.py`.
- **Impact:** `./chyg` executes standalone immediately after `curl` + `chmod +x` on any stock macOS machine.
