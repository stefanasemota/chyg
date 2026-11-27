# Development Guide (`dev.md`)

`chyg` uses only the Python standard library (compatible with macOS's built-in Python 3.9+ and Python 3.11+). No virtual environment or third-party packages are required.

## Running Locally from Source

```bash
PYTHONPATH=src python3 -m context_hygiene --version
PYTHONPATH=src python3 -m context_hygiene audit
```

## Running Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Building the Standalone Executable

```bash
python3 build.py
./chyg --version
./chyg audit --strict
```

`build.py` bundles `src/context_hygiene/` into `./chyg` using Python's built-in `zipapp` module with a `#!/usr/bin/env python3` shebang.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `CHYG_UPDATE_URL` | `https://raw.githubusercontent.com/stefanasemota/chyg/main/chyg` | Override `chyg update` HTTPS download source |
| `CHYG_INSTALL_DIR` | `~/.local/bin` (fallback `/usr/local/bin`) | Override target directory in `install.sh` |
| `NO_COLOR` | unset | Disable ANSI color output in terminal reports and TUI |
