from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

from llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI provider using JSON schema responses."""

    def __init__(self) -> None:
        load_dotenv()
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
        if not self.api_key:
            raise ValueError("Brak OPENAI_API_KEY w konfiguracji .env.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("Brak biblioteki openai. Zainstaluj zależności z requirements.txt.") from exc

        self.client = OpenAI(api_key=self.api_key)

    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Generate JSON with OpenAI structured output where supported."""
        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "prestashop_product_description",
                        "schema": schema,
                        "strict": True,
                    }
                },
                temperature=0.2,
            )
            text = response.output_text
        except Exception as first_exc:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "prestashop_product_description",
                            "schema": schema,
                            "strict": True,
                        },
                    },
                    temperature=0.2,
                )
                text = response.choices[0].message.content or ""
            except Exception as second_exc:
                raise RuntimeError(f"Błąd OpenAI API: {first_exc}; fallback chat completions: {second_exc}") from second_exc

        return _parse_json_text(text)


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Nie udało się sparsować odpowiedzi OpenAI jako JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Odpowiedź OpenAI JSON nie jest obiektem.")
    return parsed
