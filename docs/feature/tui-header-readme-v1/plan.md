# Implementation Plan — `feature/tui-header-readme-v1`

## Scope
Two targeted optimizations for `chyg` v1.0.0:

1. **README Documentation (`README.md`)**
   - Add a clear **Goal** section explaining why `chyg` exists (keeping AI coding agent instruction files lean, accurate, and free of bloat/dead paths/linter overlap on macOS).
   - Expand **How to Install** with:
     - One-line `curl` install command (including `mkdir -p ~/.local/bin` and `--version` verification) and `install.sh` alternative.
     - The two caveats: creating `~/.local/bin` if missing, and ensuring `~/.local/bin` is exported in `$PATH` (`~/.zshrc`) so `chyg` resolves from anywhere.
   - Sync the version badge to `1.0.0`.

2. **Mole-Inspired TUI Header & v1.0.0 Bump (`src/context_hygiene/tui.py`, `src/context_hygiene/__init__.py`, `pyproject.toml`)**
   - Bump version from `0.1.0` to `1.0.0` (`__version__ = "1.0.0"`, `pyproject.toml`, `README.md` badge).
   - Update `render_menu()` in `tui.py` to match the Mole layout:
     - Green ASCII art banner with the GitHub URL (`https://github.com/stefanasemota/chyg`, bold blue/cyan) and catchphrase (`Keep AI coding context lean and clean.`, green) aligned beside the banner.
     - Current version status line directly below the banner (`v1.0.0 · run chyg update to stay current`).
     - Clean `➤` selection indicator and `↑↓  |  Enter  |  Q Quit` footer.
   - Add unit test in `tests/test_cli.py` (or `tests/test_tui.py`) verifying `render_menu()` includes the GitHub URL, catchphrase, and `v1.0.0`.
   - Rebuild standalone `./chyg` via `python3 build.py` and log the v1.0.0 release & TUI update at the top of `decision.md`.

## Affected Files
- `src/context_hygiene/__init__.py` (`__version__`, `REPO_URL`, `CATCHPHRASE`)
- `src/context_hygiene/tui.py` (`render_menu()` layout & styling)
- `pyproject.toml` (version `1.0.0`)
- `README.md` (Goal section, How to Install section with caveats & `$PATH`, version badge)
- `tests/test_cli.py` (add TUI header assertions)
- `decision.md` (prepend `[27.11.2026]` ADR entry)
- `chyg` (rebuilt via `python3 build.py`)

## Trade-offs & Edge Cases
- Keep `NO_COLOR` / `use_color=False` cleanly stripping all ANSI escapes so tests and plain terminals stay readable.
- Keep zero external dependencies and Python 3.9+ / 3.11+ compatibility.

## Verification Commands
```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 build.py
./chyg --version
./chyg audit --strict
```
