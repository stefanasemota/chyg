# Repository Rules (`AGENTS.md`)

Concise project-level rules for AI coding agents working in `chyg`.

## Constraints
- **Zero External Dependencies:** Use Python standard library modules only. Keep compatibility with macOS's built-in Python 3.9+ and Python 3.11+.
- **macOS TCC Safety:** Never walk `$HOME`, `~/Desktop`, `~/Documents`, `~/Downloads`, or `~/Library` without explicit confirmation, and never follow symlinks escaping the scan root.
- **Rebuild Executable:** Whenever files under `src/context_hygiene/` change, run `python3 build.py` to refresh `./chyg` before committing.

## Verification
- Run `PYTHONPATH=src python3 -m unittest discover -s tests -v` and confirm all tests pass.
- Run `./chyg audit --strict` to verify repository instruction files stay lean.
- Use Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`) and log architectural changes at the top of `decision.md` using `[DD.MM.YYYY]` format.
