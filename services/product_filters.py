from __future__ import annotations

import json
from typing import Any

import pandas as pd

CAMERA_FILTER_SUGGESTIONS = [
    "Typ kamery",
    "Seria",
    "Rozdzielczość",
    "Ogniskowa",
    "Kąt widzenia",
    "Zasięg IR",
    "Kompresja",
    "Przetwornik",
    "Klasa szczelności",
    "Klasa wandaloodporności",
    "Zasilanie",
    "PoE",
    "Karta pamięci",
    "Mikrofon",
    "Funkcje AI",
]

GENERIC_FILTER_SUGGESTIONS = [
    "Producent",
    "Seria",
    "Typ produktu",
    "Zastosowanie",
    "Napięcie",
    "Prąd",
    "Moc",
    "Stopień ochrony IP",
    "Materiał",
    "Wymiary",
    "Kolor",
    "Montaż",
]


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if _is_empty(value):
        return default
    return str(value).strip().lower() in {"1", "true", "tak", "yes", "y"}


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() in {"", "none", "nan", "null"}


def _clean_text(value: Any) -> str:
    if _is_empty(value):
        return ""
    return str(value).strip()


def normalize_filters(filters: Any) -> list[dict[str, Any]]:
    """Normalize LLM or UI filter data to rows with name, value and source."""
    normalized: list[dict[str, Any]] = []
    if not isinstance(filters, list):
        return normalized

    for item in filters:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name", ""))
        value = _clean_text(item.get("value", ""))
        source = _clean_text(item.get("source", ""))
        enabled = _to_bool(item.get("enabled", False))
        if not name:
            continue
        normalized.append({"enabled": enabled, "name": name, "value": value, "source": source})

    return normalized


def filters_to_json(filters: list[dict[str, Any]]) -> str:
    """Serialize filters for storage in XLSX."""
    return json.dumps(normalize_filters(filters), ensure_ascii=False)


def filters_from_json(value: Any) -> list[dict[str, Any]]:
    """Load filters stored in an XLSX cell."""
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return normalize_filters(parsed)


def filters_to_features_text(filters: list[dict[str, Any]]) -> str:
    """Build a readable PrestaShop feature string from enabled filter rows."""
    parts: list[str] = []
    for item in normalize_filters(filters):
        if not item["enabled"]:
            continue
        name = item["name"]
        value = item["value"]
        if name and value and value.lower() != "brak danych w karcie katalogowej":
            parts.append(f"{name}: {value}")
    return " | ".join(parts)


def filters_to_disabled_text(filters: list[dict[str, Any]]) -> str:
    """Build a readable list of filters explicitly excluded by the operator."""
    parts: list[str] = []
    for item in normalize_filters(filters):
        if item["enabled"]:
            continue
        name = item["name"]
        value = item["value"]
        if name:
            parts.append(f"{name}: {value}" if value else name)
    return " | ".join(parts)


def default_filter_rows(product_name: str) -> list[dict[str, Any]]:
    """Return no automatic filters; operators add/select filters manually."""
    return []


def update_product_filters(df: pd.DataFrame, id_product: str | int, filters: list[dict[str, Any]]) -> pd.DataFrame:
    """Store product filters in JSON and readable feature columns."""
    updated = df.copy().fillna("")
    for column in ("filters_json", "features", "disabled_features"):
        if column not in updated.columns:
            updated[column] = ""

    if "id_product" not in updated.columns:
        raise ValueError("Arkusz nie zawiera wymaganej kolumny id_product.")

    product_id = str(id_product).strip()
    mask = updated["id_product"].astype(str).str.strip() == product_id
    if not mask.any():
        raise ValueError(f"Nie znaleziono produktu o id_product={id_product}.")

    normalized = normalize_filters(filters)
    updated.loc[mask, "filters_json"] = filters_to_json(normalized)
    updated.loc[mask, "features"] = filters_to_features_text(normalized)
    updated.loc[mask, "disabled_features"] = filters_to_disabled_text(normalized)
    return updated
