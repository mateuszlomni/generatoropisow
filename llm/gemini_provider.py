from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

from llm.base import LLMProvider


class GeminiProvider(LLMProvider):
    """Google Gemini provider using the official google-genai package."""

    def __init__(self) -> None:
        load_dotenv()
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
        if not self.api_key:
            raise ValueError("Brak GEMINI_API_KEY w konfiguracji .env.")

        try:
            from google import genai
        except ImportError as exc:
            raise ImportError("Brak biblioteki google-genai. Zainstaluj zależności z requirements.txt.") from exc

        self.client = genai.Client(api_key=self.api_key)

    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Generate JSON with Gemini structured output where supported."""
        try:
            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.2,
                ),
            )
        except TypeError:
            response = self.client.models.generate_content(
                model=self.model,
                contents=f"{system_prompt}\n\n{user_prompt}",
            )
        except Exception as exc:
            raise RuntimeError(f"Błąd Gemini API: {exc}") from exc

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, dict):
            return parsed

        text = getattr(response, "text", None)
        if not text:
            raise ValueError("Gemini nie zwrócił tekstu ani sparsowanego JSON.")

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
        raise ValueError(f"Nie udało się sparsować odpowiedzi Gemini jako JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Odpowiedź Gemini JSON nie jest obiektem.")
    return parsed
