from __future__ import annotations

from html import escape
from typing import Any

from bs4 import BeautifulSoup

from llm.base import LLMProvider
from prompts.product_description_prompt import build_system_prompt, build_user_prompt
from services.validators import clean_html, validate_llm_response

CATALOG_TEXT_LIMIT = 80_000
DESCRIPTION_SHORT_LIMIT = 500

DESCRIPTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description_short": {"type": "string"},
        "description": {"type": "string"},
        "filters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["name", "value", "source"],
                "additionalProperties": False,
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
        "missing_data": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["description_short", "description", "filters", "warnings", "missing_data"],
    "additionalProperties": False,
}


def limit_catalog_text(catalog_text: str, limit: int = CATALOG_TEXT_LIMIT) -> tuple[str, bool]:
    """Limit long catalog text before sending it to an LLM provider."""
    if len(catalog_text) <= limit:
        return catalog_text, False
    return catalog_text[:limit], True


def generate_product_description(
    provider: LLMProvider,
    product_name: str,
    reference: str,
    catalog_text: str,
) -> dict[str, Any]:
    """Generate and validate a PrestaShop description for one product."""
    limited_text, was_truncated = limit_catalog_text(catalog_text)
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(product_name=product_name, reference=reference, catalog_text=limited_text)

    data = provider.generate_json(system_prompt=system_prompt, user_prompt=user_prompt, schema=DESCRIPTION_SCHEMA)

    if isinstance(data.get("description_short"), str):
        data["description_short"] = enforce_description_short_limit(clean_html(data["description_short"]))
    if isinstance(data.get("description"), str):
        data["description"] = clean_html(data["description"])

    if was_truncated:
        warnings = data.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append("Tekst karty katalogowej został skrócony do 80 000 znaków przed wysłaniem do LLM.")

    is_valid, errors = validate_llm_response(data)
    if not is_valid:
        raise ValueError("Niepoprawna odpowiedź LLM: " + " ".join(errors))

    return data


def enforce_description_short_limit(html: str, limit: int = DESCRIPTION_SHORT_LIMIT) -> str:
    """Ensure description_short is a single paragraph not exceeding PrestaShop's limit."""
    cleaned = clean_html(html)
    if len(cleaned) <= limit:
        return cleaned

    text = BeautifulSoup(cleaned, "html.parser").get_text(" ", strip=True)
    wrapper_length = len("<p></p>")
    max_text_length = max(limit - wrapper_length, 0)

    if len(text) > max_text_length:
        suffix = "..."
        text = text[: max(max_text_length - len(suffix), 0)].rstrip() + suffix

    shortened = f"<p>{escape(text)}</p>"
    if len(shortened) <= limit:
        return shortened

    return shortened[: limit - len("</p>")].rstrip() + "</p>"
