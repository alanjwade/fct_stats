"""
Shared meet-name configuration loaded from config/meet_names.yaml.

Provides:
    normalize_meet_name(raw)  – apply the name_mapping
    excluded_from_records()   – set of canonical names to hide from records pages
"""

from pathlib import Path
import yaml

_CONFIG_PATH = Path(__file__).parent.parent / 'config' / 'meet_names.yaml'
_config = None


def _load():
    global _config
    if _config is None:
        with open(_CONFIG_PATH, 'r') as f:
            _config = yaml.safe_load(f)
    return _config


def normalize_meet_name(name: str) -> str:
    """Return the canonical meet name, or the original if no mapping exists."""
    mapping = _load().get('name_mapping', {})
    return mapping.get(name, name)


def excluded_from_records() -> set:
    """Return the set of canonical meet names excluded from all-time records."""
    return set(_load().get('excluded_from_records', []))
