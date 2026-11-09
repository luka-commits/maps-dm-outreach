"""Repo paths, config and secrets in one place. Nothing here is machine specific."""
from __future__ import annotations

import json
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCHEMA = ROOT / "app" / "lib" / "schema.sql"
CONFIG_FILE = ROOT / "outreach.config.json"
CONFIG_EXAMPLE = ROOT / "outreach.config.example.json"
STRATEGIES = ROOT / "strategies" / "strategies.json"
ENV_FILE = ROOT / ".env"


def load_env(path: pathlib.Path | None = None) -> None:
    """Read KEY=VALUE lines from the repo-root .env into os.environ (existing variables win)."""
    path = path or ENV_FILE
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("\"'")
        if key.strip() and value:
            os.environ.setdefault(key.strip(), value)


def apify_token() -> str | None:
    load_env()
    return os.environ.get("APIFY_TOKEN") or None


def db_path() -> pathlib.Path:
    load_env()
    return pathlib.Path(os.environ.get("OUTREACH_DB") or DATA / "leads.db")


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict:
    """outreach.config.json over the example. Missing file or keys fall back to the example."""
    base = json.loads(CONFIG_EXAMPLE.read_text(encoding="utf-8")) if CONFIG_EXAMPLE.is_file() else {}
    if CONFIG_FILE.is_file():
        try:
            return _merge(base, json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return base


def atomic_json(path: pathlib.Path, value) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
