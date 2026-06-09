from __future__ import annotations

from typing import Any

from llm.base import LLMProvider


class MockProvider(LLMProvider):
    """Local provider for testing the UI without API calls."""

    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "description_short": (
                "<p><strong>Produkt testowy</strong> to przykładowy opis wygenerowany w trybie mock "
                "na potrzeby sprawdzenia interfejsu aplikacji.</p>"
            ),
            "description": (
                "<h2>Produkt testowy</h2>"
                "<p><strong>Produkt testowy</strong> to przykładowy opis techniczny przygotowany bez "
                "wywołania zewnętrznego API.</p>"
                "<h3>Zastosowanie</h3>"
                "<p>Tryb mock służy wyłącznie do testów działania aplikacji.</p>"
                "<h3>Najważniejsze cechy</h3>"
                "<ul><li>Opis wygenerowany lokalnie.</li><li>Brak kosztów API.</li></ul>"
                "<h3>Dane techniczne</h3>"
                "<table><tbody><tr><td>Źródło</td><td>tryb mock</td></tr></tbody></table>"
                "<h3>Informacje dodatkowe</h3>"
                "<p>Dane techniczne należy uzupełnić na podstawie właściwej karty katalogowej.</p>"
            ),
            "filters": [
                {"name": "Tryb", "value": "mock", "source": "odpowiedź testowa"},
                {"name": "Źródło danych", "value": "brak rzeczywistej karty", "source": "tryb mock"},
            ],
            "warnings": ["To jest odpowiedź testowa z mock providera, nie na podstawie karty katalogowej."],
            "missing_data": ["Brak rzeczywistej analizy dokumentacji w trybie mock."],
        }
