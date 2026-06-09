from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, ValidationError

REQUIRED_LLM_FIELDS = {"description_short", "description", "warnings", "missing_data"}
FORBIDDEN_TAGS = {"script", "style", "iframe", "img", "a", "meta", "link", "html", "body", "head"}
ALLOWED_TAGS = {"h2", "h3", "p", "strong", "ul", "li", "table", "tbody", "tr", "td"}
MARKDOWN_MARKERS = ("```", "```html", "```json")


class LLMDescriptionResponse(BaseModel):
    """Strict model for the JSON returned by LLM providers."""

    model_config = ConfigDict(extra="forbid")

    description_short: str
    description: str
    warnings: list[str]
    missing_data: list[str]


def validate_llm_response(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate provider output before it reaches the editable UI."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return False, ["Odpowiedź LLM nie jest obiektem JSON."]

    try:
        LLMDescriptionResponse.model_validate(data)
    except ValidationError as exc:
        errors.append(f"Struktura JSON jest niepoprawna: {exc}")

    missing_fields = REQUIRED_LLM_FIELDS - set(data.keys())
    if missing_fields:
        errors.append(f"Brak wymaganych pól JSON: {', '.join(sorted(missing_fields))}.")

    if not isinstance(data.get("description_short"), str):
        errors.append("Pole description_short musi być tekstem.")

    if not isinstance(data.get("description"), str):
        errors.append("Pole description musi być tekstem.")

    if not isinstance(data.get("warnings"), list):
        errors.append("Pole warnings musi być listą.")

    if not isinstance(data.get("missing_data"), list):
        errors.append("Pole missing_data musi być listą.")

    if isinstance(data.get("description_short"), str) and len(data["description_short"]) > 500:
        errors.append("Pole description_short przekracza 500 znaków.")

    for field in ("description_short", "description"):
        value = data.get(field)
        if isinstance(value, str):
            valid_html, html_errors = validate_html(value)
            errors.extend([f"{field}: {error}" for error in html_errors])
            if not valid_html:
                continue

    return not errors, errors


def validate_html(html: str) -> tuple[bool, list[str]]:
    """Check generated HTML for forbidden tags and Markdown fences."""
    errors: list[str] = []

    if any(marker in html for marker in MARKDOWN_MARKERS):
        errors.append("HTML nie może zawierać bloków Markdown ani znaczników ```.")

    soup = BeautifulSoup(html or "", "html.parser")
    found_forbidden = sorted({tag.name for tag in soup.find_all() if tag.name in FORBIDDEN_TAGS})
    if found_forbidden:
        errors.append(f"HTML zawiera zabronione tagi: {', '.join(found_forbidden)}.")

    found_unknown = sorted(
        {tag.name for tag in soup.find_all() if tag.name not in ALLOWED_TAGS and tag.name not in FORBIDDEN_TAGS}
    )
    if found_unknown:
        errors.append(f"HTML zawiera niedozwolone tagi: {', '.join(found_unknown)}.")

    return not errors, errors


def clean_html(html: str) -> str:
    """Remove dangerous tags, attributes, comments and Markdown fences from generated HTML."""
    cleaned = html or ""
    for marker in MARKDOWN_MARKERS:
        cleaned = cleaned.replace(marker, "")

    soup = BeautifulSoup(cleaned, "html.parser")

    for tag in soup.find_all(FORBIDDEN_TAGS):
        tag.decompose()

    for tag in soup.find_all():
        tag.attrs = {}
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()

    return str(soup).strip()
