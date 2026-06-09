from __future__ import annotations

import os

from dotenv import load_dotenv

from llm.base import LLMProvider
from llm.gemini_provider import GeminiProvider
from llm.mock_provider import MockProvider
from llm.openai_provider import OpenAIProvider


def get_llm_provider() -> LLMProvider:
    """Create an LLM provider selected through the LLM_PROVIDER environment variable."""
    load_dotenv()
    provider_name = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

    if provider_name == "gemini":
        return GeminiProvider()
    if provider_name == "openai":
        return OpenAIProvider()
    if provider_name == "mock":
        return MockProvider()

    raise ValueError("Nieobsługiwany LLM_PROVIDER. Dozwolone wartości: gemini, openai, mock.")
