from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Common interface for providers that return JSON-like dictionaries."""

    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Generate a response as a Python dictionary matching the provided schema."""
        raise NotImplementedError
