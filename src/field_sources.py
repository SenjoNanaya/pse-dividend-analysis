"""Per-field provenance tags for financial metrics (html / pdf / backfill / …)."""
from __future__ import annotations

import json
from typing import Any

VALID_SOURCES = frozenset(
    {"html", "pdf", "backfill", "derived", "form17c", "disclosure"}
)

# Parser / in-memory keys → DB column names used on insert
KEY_TO_DB = {
    "gross_revenue": "revenue",
    "book_value_per_share": "book_value",
}

META_KEYS = frozenset(
    {
        "_field_sources",
        "operating_income_derived",
        "gross_profit_derived",
        "statement_scope",
        "scale",
    }
)


def set_source(row: dict[str, Any], key: str, source: str) -> None:
    if source not in VALID_SOURCES:
        return
    if key in META_KEYS or key.startswith("_"):
        return
    sources = row.setdefault("_field_sources", {})
    if not isinstance(sources, dict):
        sources = {}
        row["_field_sources"] = sources
    sources[key] = source


def init_sources_from_metrics(row: dict[str, Any], source: str = "html") -> dict[str, Any]:
    """Tag every present non-meta metric as ``source`` (mutates row)."""
    out = dict(row.get("_field_sources") or {})
    for k, v in row.items():
        if k in META_KEYS or k.startswith("_"):
            continue
        if v is None:
            continue
        out[k] = source
    row["_field_sources"] = out
    return out


def apply_derived_flags(row: dict[str, Any]) -> None:
    """After sanitize_operating_metrics, tag synthesized GP/OI as derived."""
    if row.get("gross_profit_derived"):
        set_source(row, "gross_profit", "derived")
    if row.get("operating_income_derived"):
        set_source(row, "operating_income", "derived")


def remap_sources_for_db(sources: dict[str, Any] | None) -> dict[str, str]:
    """Map in-memory metric keys to financials column names."""
    if not sources:
        return {}
    out = {}
    for k, v in sources.items():
        if v not in VALID_SOURCES:
            continue
        db_key = KEY_TO_DB.get(k, k)
        out[db_key] = v
    return out


def sources_to_json(sources: dict[str, Any] | None) -> str | None:
    remapped = remap_sources_for_db(sources)
    if not remapped:
        return None
    return json.dumps(remapped, sort_keys=True)


def sources_from_json(raw) -> dict[str, str]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if v in VALID_SOURCES}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v in VALID_SOURCES}


def merge_source_tags(existing: dict[str, str], filled_cols: list[str], source: str) -> dict[str, str]:
    out = dict(existing or {})
    for col in filled_cols:
        out[col] = source
    return out
