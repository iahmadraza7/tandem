"""Load niche playbooks. Adding a niche = adding one YAML file here."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PLAYBOOK_DIR = Path(__file__).parent


@lru_cache
def all_playbooks() -> dict[str, dict[str, Any]]:
    books = {}
    for path in sorted(PLAYBOOK_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        books[data["name"]] = data
    return books


def get(name: str) -> dict[str, Any]:
    books = all_playbooks()
    if name not in books:
        raise KeyError(f"Unknown playbook: {name}")
    return books[name]


def guess(text: str) -> str | None:
    """Keyword fallback when no LLM is configured."""
    lowered = text.lower()
    best, best_hits = None, 0
    for name, book in all_playbooks().items():
        hits = sum(1 for kw in book.get("keywords", []) if kw in lowered)
        if hits > best_hits:
            best, best_hits = name, hits
    return best


def fill(template: str, values: dict[str, Any]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", "" if value is None else str(value))
    return out


def consent_template(name: str, values: dict[str, Any]) -> list[dict[str, Any]]:
    """Consent card rows with defaults filled from the request."""
    rows = []
    for row in get(name)["consent_fields"]:
        rows.append(
            {
                "key": row["key"],
                "label": row["label"],
                "value": fill(row.get("default", ""), values),
                "share": bool(row.get("share_by_default", False)),
            }
        )
    return rows
