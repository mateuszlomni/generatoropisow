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
        "katalogowej. Jeśli dokumentacja obejmuje wiele wariantów, używasz tylko danych "
        "jednoznacznie przypisanych do wybranej referencji albo całej serii. Nie przenosisz "
        "parametrów z innego modelu. Wyodrębniasz także filtry/cechy produktu do PrestaShop, ale "
        "tylko wtedy, gdy ich wartości są jawnie obecne w karcie katalogowej. Zwracasz wyłącznie poprawny JSON zgodny ze schematem. Nie "
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

Karty wspólne dla wielu wariantów:
- Jeśli karta katalogowa opisuje kilka modeli, wariantów albo referencji, używaj tylko danych,
  które są jawnie przypisane do nazwy produktu, referencji albo całej serii bez rozróżnienia wariantów.
- Nie kopiuj parametrów z innego symbolu/modelu tylko dlatego, że jest w tej samej karcie.
- Jeśli nie da się jednoznacznie dopasować parametrów do referencji "{reference}", napisz opis neutralny,
  dodaj ostrzeżenie w warnings i wpisz brakujące dane w missing_data.
- Dla produktów akcesoryjnych bez osobnej karty nie zgaduj funkcji głównego urządzenia.

Wymagania dla description_short:
- HTML.
- Jeden akapit <p>...</p>.
- Bezwzględnie maksymalnie 500 znaków razem ze znacznikami HTML; celuj w 420-460 znaków.
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

Wymagania dla filters:
- Zwróć listę obiektów z polami name, value, source.
- name to nazwa filtra/cechy, np. "Rozdzielczość", "Ogniskowa", "Zasilanie".
- value to wartość dokładnie na podstawie karty katalogowej.
- source to krótki cytat albo fragment źródłowy z karty, z którego wynika wartość.
- Nie dodawaj filtrów, których wartości nie ma w karcie.
- Jeśli produkt jest kamerą, spróbuj wyciągnąć: Typ kamery, Seria, Rozdzielczość, Ogniskowa, Kąt widzenia, Zasięg IR, Kompresja, Przetwornik, Klasa szczelności, Klasa wandaloodporności, Zasilanie, PoE, Karta pamięci, Mikrofon, Funkcje AI.
- Jeśli któregoś ważnego filtra dla kamery nie ma w karcie, nie wymyślaj wartości; dodaj informację do missing_data.
- Dla produktów innych niż kamery dobierz tylko sensowne filtry wynikające z dokumentacji, np. typ produktu, seria, napięcie, prąd, moc, IP, montaż, materiał, wymiary.

Zwróć tylko JSON:
{{
  "description_short": "...",
  "description": "...",
  "filters": [
    {{"name": "Rozdzielczość", "value": "5 MP", "source": "rozdzielczość 5 MP"}},
    {{"name": "Ogniskowa", "value": "2.8 mm", "source": "obiektyw o stałej ogniskowej 2.8 mm"}}
  ],
  "warnings": [],
  "missing_data": []
}}
""".strip()
