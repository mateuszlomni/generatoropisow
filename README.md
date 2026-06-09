# Generator opisów produktów PrestaShop

Aplikacja Streamlit do półautomatycznego generowania opisów produktów dla sklepu PrestaShop na podstawie pliku Excel z produktami oraz kart katalogowych producenta.

Narzędzie jest przeznaczone do pracy operatora: człowiek wybiera produkt, wgrywa kartę katalogową, generuje opis przez LLM, ręcznie sprawdza i poprawia wynik, a dopiero potem zapisuje opis do arkusza.

## Najważniejsza zasada

Aplikacja i prompt są przygotowane tak, aby nie wymyślać danych technicznych. Model może używać tylko informacji jawnie obecnych w karcie katalogowej albo bezpośrednio wynikających z nazwy produktu i referencji.

Jeśli parametr nie występuje w dokumentacji, powinien zostać pominięty albo oznaczony jako `brak danych w karcie katalogowej`. Operator powinien zawsze zweryfikować opis przed importem do PrestaShop.

## Obsługiwany Excel

Aplikacja obsługuje pliki XLSX podobne do `produkty_podzielone_partie_po_40.xlsx`.

Arkusz `Podsumowanie` jest ignorowany przy wyborze produktów. Arkusze `Partia X` powinny zawierać kolumny:

- `id_product`
- `product_name`
- `reference`
- `description`
- `description_short`

Jeśli kolumny `description` albo `description_short` nie istnieją, aplikacja utworzy je podczas zapisu w pamięci.

## Funkcje

- upload pliku XLSX,
- wybór arkusza / partii,
- filtrowanie produktów bez opisów,
- wybór jednego produktu,
- upload karty katalogowej PDF, DOCX lub TXT,
- obowiązkowe załączenie minimum 2 zdjęć produktu przed zapisem,
- podgląd załączonych zdjęć,
- odczyt tekstu z dokumentu,
- generowanie `description_short` i `description`,
- edycja wygenerowanego HTML przed zapisem,
- automatyczne wyciąganie filtrów/cech z karty katalogowej,
- ręczna edycja filtrów/cech przez operatora,
- podgląd wygenerowanego HTML przed zapisem,
- zapis opisu do wybranego wiersza w pamięci aplikacji,
- pobranie zaktualizowanego XLSX,
- pobranie CSV do importu PrestaShop z kolumnami `id_product`, `description_short`, `description`, `features`, `image_1`, `image_2`, `operator`.

## Praca dla wielu operatorów

Aplikacja jest przygotowana do scenariusza, w którym wysyłasz jeden link wielu osobom. Każdy operator pracuje w swojej sesji przeglądarki:

1. wpisuje hasło dostępu, jeśli zostało ustawione,
2. podaje imię lub inicjały w polu `Operator`,
3. wgrywa przydzielony plik Excel albo partię,
4. uzupełnia produkty na podstawie kart katalogowych,
5. pobiera gotowy XLSX/CSV i odsyła go koordynatorowi.

Dane są trzymane w pamięci sesji użytkownika. Aplikacja nie tworzy wspólnej bazy ani nie scala wyników od 75 osób automatycznie. To celowo prostszy i bezpieczniejszy tryb: każdy operator oddaje swój plik wynikowy.

## Zdjęcia produktów

Przed zapisem opisu operator musi załączyć minimum dwa zdjęcia produktu. Aplikacja pokazuje miniatury zdjęć i zapisuje nazwy dwóch pierwszych plików w kolumnach `image_1` oraz `image_2` w eksporcie XLSX/CSV.

Pierwsze zdjęcie traktuj jako główne zdjęcie PrestaShop, a drugie jako zdjęcie dodatkowe lub materiał do szablonu produktu.

Wersja webowa nie przechowuje zdjęć na stałe po zakończeniu sesji. Do importu PrestaShop zdjęcia powinny zostać osobno umieszczone w miejscu dostępnym dla sklepu, np. jako pliki na serwerze lub publiczne adresy URL zgodnie z docelowym procesem importu.

## Filtry i cechy PrestaShop

AI próbuje wyciągnąć filtry/cechy produktu z karty katalogowej i pokazuje je w edytowalnej tabeli. Operator może poprawić wartości albo dopisać brakujące parametry ręcznie, ale tylko po sprawdzeniu dokumentacji.

Dla kamer aplikacja szczególnie pilnuje parametrów takich jak:

- typ kamery,
- seria,
- rozdzielczość,
- ogniskowa,
- kąt widzenia,
- zasięg IR,
- kompresja,
- przetwornik,
- klasa szczelności IP,
- klasa wandaloodporności IK,
- zasilanie,
- PoE,
- karta pamięci,
- mikrofon,
- funkcje AI.

Jeśli wartości nie ma w karcie katalogowej, AI ma ją pominąć i dopisać informację do brakujących danych. W XLSX filtry są zapisywane w kolumnach `filters_json` oraz `features`. CSV eksportuje kolumnę `features` w formacie czytelnym do dalszego mapowania w imporcie PrestaShop.

## Instalacja

1. Utwórz środowisko wirtualne:

```bash
python -m venv .venv
```

2. Aktywuj środowisko:

Windows:

```powershell
.venv\Scripts\activate
```

Linux/Mac:

```bash
source .venv/bin/activate
```

3. Zainstaluj zależności:

```bash
pip install -r requirements.txt
```

4. Utwórz plik `.env` na podstawie `.env.example`:

```bash
cp .env.example .env
```

W Windows możesz też skopiować plik ręcznie.

5. Uruchom aplikację:

```bash
streamlit run app.py
```

## Konfiguracja LLM

Provider wybiera zmienna:

```env
LLM_PROVIDER=gemini
```

Obsługiwane wartości:

- `gemini`
- `openai`
- `mock`

Tryb `mock` nie korzysta z API i służy do testowania interfejsu.

## Hasło dostępu

Dla wdrożenia publicznego ustaw zmienną:

```env
APP_PASSWORD=ustaw_tajne_haslo
```

Jeśli `APP_PASSWORD` jest puste, aplikacja działa bez ekranu logowania. Przy wysyłce linku do wielu osób zalecane jest ustawienie hasła oraz użycie jednego wspólnego hasła operacyjnego albo osobnej instancji dla każdej grupy.

## Gemini

W pliku `.env` ustaw:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=twoj_klucz
GEMINI_MODEL=gemini-2.5-flash
```

Aplikacja używa oficjalnej biblioteki `google-genai` i próbuje wymusić odpowiedź JSON zgodną ze schematem.

## OpenAI

W pliku `.env` ustaw:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=twoj_klucz
OPENAI_MODEL=gpt-4.1-mini
```

OpenAI jest opcjonalnym drugim providerem. Odpowiedź ma taki sam format jak w Gemini.

## Deploy

Projekt zawiera pliki ułatwiające wdrożenie:

- `.streamlit/config.toml` - konfiguracja Streamlit dla środowiska serwerowego,
- `Dockerfile` - uruchomienie aplikacji w kontenerze,
- `Procfile` - wariant dla platform typu Render/Heroku,
- `runtime.txt` - wskazanie Pythona 3.11 dla hostingu obsługującego ten format.

Najprostszy wariant dla 75 osób to jeden web service na Render, Railway, Fly.io albo VPS z Dockerem. Po wdrożeniu wysyłasz operatorom URL aplikacji, hasło, ich partie XLSX i instrukcję pobrania gotowego pliku po zakończeniu pracy.

### Docker

```bash
docker build -t prestashop-opisy .
docker run -p 8501:8501 --env-file .env prestashop-opisy
```

### Streamlit Community Cloud

1. Wgraj projekt do repozytorium Git.
2. Ustaw główny plik aplikacji jako `app.py`.
3. Dodaj sekrety odpowiadające plikowi `.env.example`.
4. Uruchom aplikację.

Przykład sekretów dla Streamlit Cloud:

```toml
LLM_PROVIDER = "gemini"
GEMINI_API_KEY = "twoj_klucz"
GEMINI_MODEL = "gemini-2.5-flash"
OPENAI_API_KEY = ""
OPENAI_MODEL = "gpt-4.1-mini"
APP_PASSWORD = "ustaw_tajne_haslo"
```

### Render

Możesz użyć `Procfile` albo wdrożenia Docker. W zmiennych środowiskowych ustaw `LLM_PROVIDER` oraz odpowiednie klucze API.

## Bezpieczeństwo danych i kosztów

Aplikacja nie wysyła całego Excela do LLM. Do providera trafiają tylko:

- nazwa wybranego produktu,
- referencja,
- tekst wgranej karty katalogowej.

Długie karty katalogowe są skracane do 80 000 znaków przed wysłaniem do LLM. Aplikacja nie zapisuje wgranych dokumentów na stałe.

## Ograniczenia pierwszej wersji

- PDF-y skanowane nie są rozpoznawane przez OCR.
- Formatowanie oryginalnego Excela może nie zostać zachowane przy eksporcie, ale arkusze i dane są zachowywane.
- Import do PrestaShop należy wykonać dopiero po ręcznej kontroli wygenerowanych opisów.
