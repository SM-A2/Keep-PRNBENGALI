"""Tiny .env loader (no extra dependency).

Botkeep writes the Environment tab into a .env file in the project root and does NOT inject it
for you -- the Python code has to load it (docs: botkeep.cloud/docs/python). Real process
environment variables always win over the file.
"""
import os
from pathlib import Path


def load_env(path: str | Path | None = None) -> int:
    file = Path(path) if path else Path(__file__).parent / ".env"
    if not file.is_file():
        return 0
    loaded = 0
    for raw in file.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded
