from __future__ import annotations

from typing import Any

from llm.base import LLMProvider
from prompts.product_description_prompt import build_system_prompt, build_user_prompt
from services.validators import clean_html, validate_llm_response

CATALOG_TEXT_LIMIT = 80_000

DESCRIPTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description_short": {"type": "string"},
        "description": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "missing_data": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["description_short", "description", "warnings", "missing_data"],
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
        data["description_short"] = clean_html(data["description_short"])
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
