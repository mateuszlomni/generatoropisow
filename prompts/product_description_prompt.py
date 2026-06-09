from __future__ import annotations


def build_system_prompt() -> str:
    """Return the system prompt enforcing source-grounded technical descriptions."""
    return (
        "Jesteś specjalistą ds. opisów technicznych produktów dla sklepu PrestaShop "
        "z branży elektrycznej, automatyki, sterowania, zabezpieczeń i osprzętu "
        "instalacyjnego. Tworzysz opisy po polsku na podstawie danych wejściowych "
        "i treści karty katalogowej. Nie wolno Ci wymyślać żadnych danych technicznych. "
        "Możesz używać tylko informacji jawnie obecnych w karcie katalogowej lub "
        "bezpośrednio wynikających z nazwy produktu i referencji. Jeśli parametr nie "
        "występuje w dokumentacji, pomiń go albo oznacz jako brak danych w karcie "
        "katalogowej. Zwracasz wyłącznie poprawny JSON zgodny ze schematem. Nie "
        "zwracasz Markdown. Nie dodajesz komentarzy poza JSON."
    )


def build_user_prompt(product_name: str, reference: str, catalog_text: str) -> str:
    """Build the user prompt with product data and extracted catalog text."""
    return f"""
Nazwa produktu: {product_name}
Referencja: {reference}

Treść karty katalogowej:
---
{catalog_text}
---

Na podstawie powyższej karty katalogowej wygeneruj opis produktu do PrestaShop.

Najważniejsza zasada:
Nie dodawaj żadnych parametrów, których nie ma w karcie katalogowej. Nie dopisuj
napięcia, prądu, stopnia ochrony IP, wymiarów, materiału, norm, certyfikatów,
zastosowań ani kompatybilności, jeśli nie są jawnie obecne w źródle.

Wymagania dla description_short:
- HTML.
- Jeden akapit <p>...</p>.
- Maksymalnie 500 znaków.
- Bez tabel, Markdown i nagłówków.
- Musi zawierać nazwę produktu.
- Naturalny styl sprzedażowo-techniczny bez przesadnego marketingu.

Wymagania dla description:
- HTML zgodny z PrestaShop, bez Markdown.
- Bez tagów <html>, <head>, <body>, CSS, linków, zdjęć i emoji.
- Dozwolone tagi: h2, h3, p, strong, ul, li, table, tbody, tr, td.
- Opis po polsku, techniczny i profesjonalny.
- Jeśli karta katalogowa zawiera dane techniczne, umieść je w tabeli.
- Jeśli brakuje danych do danego pola, pomiń wiersz albo wpisz "brak danych w karcie katalogowej".

Zwróć tylko JSON:
{{
  "description_short": "...",
  "description": "...",
  "warnings": [],
  "missing_data": []
}}
""".strip()
