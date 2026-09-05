"""Load local .env without exposing secrets.

Existing process environment wins. Values are never printed.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_LOADED = False


def load_runtime_env() -> Path | None:
    global _LOADED
    path = Path(ROOT / '.env')
    if _LOADED:
        return path if path.is_file() else None
    try:
        from dotenv import load_dotenv
    except ImportError:
        _LOADED = True
        return None
    if path.is_file():
        load_dotenv(path, override=False)
    _LOADED = True
    return path if path.is_file() else None


def masked(name: str) -> str:
    value = __import__('os').getenv(name, '').strip()
    if not value:
        return 'missing'
    return f'set ({len(value)} chars)'
