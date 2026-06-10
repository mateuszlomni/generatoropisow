# Generator opisów produktów PrestaShop

Aplikacja Streamlit do półautomatycznego generowania opisów produktów dla sklepu PrestaShop na podstawie centralnej bazy Supabase, Excela z produktami oraz kart katalogowych producenta.

Narzędzie jest przeznaczone do pracy wielu operatorów: administrator importuje główny Excel raz do Supabase, operatorzy wybierają produkty z centralnej listy, widzą status uzupełnienia, wgrywają kartę katalogową i zdjęcia, generują opis przez LLM, ręcznie sprawdzają wynik, a dopiero potem zapisują dane do bazy.

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

Excel jest importowany do Supabase. Po imporcie operatorzy nie wgrywają już swoich kopii Excela do pracy bieżącej, tylko pracują na centralnej liście produktów.

## Funkcje

- import pliku XLSX do Supabase przez administratora,
- wybór arkusza / partii z centralnej bazy,
- wspólny status produktu: do uzupełnienia / uzupełnione,
- filtrowanie produktów bez opisów,
- wybór jednego produktu,
- upload karty katalogowej PDF, DOCX lub TXT,
- obowiązkowe załączenie minimum 1 zdjęcia produktu przed zapisem,
- podgląd załączonych zdjęć,
- odczyt tekstu z dokumentu,
- generowanie `description_short` i `description`,
- edycja wygenerowanego HTML przed zapisem,
- automatyczne wyciąganie filtrów/cech z karty katalogowej,
- ręczna edycja filtrów/cech przez operatora,
- podgląd wygenerowanego HTML przed zapisem,
- zapis opisu, filtrów, statusu, zdjęć i karty katalogowej do Supabase,
- upload zdjęć i kart katalogowych do Supabase Storage,
- pobranie XLSX/CSV z bieżącej partii na podstawie danych z bazy.

## Praca dla wielu operatorów

Aplikacja jest przygotowana do scenariusza, w którym wysyłasz jeden link wielu osobom. Każdy operator pracuje na tej samej bazie Supabase:

1. wpisuje hasło dostępu, jeśli zostało ustawione,
2. podaje imię lub inicjały w polu `Operator`,
3. wybiera partię i produkt z centralnej listy,
4. widzi, które produkty są już uzupełnione,
5. uzupełnia produkty na podstawie kart katalogowych,
6. zapisuje wynik do Supabase.

Dane nie są trzymane jako główne źródło prawdy w pamięci sesji Streamlit. Supabase przechowuje produkty, statusy, opisy, filtry, operatora oraz ścieżki do plików.

## Zdjęcia produktów

Przed zapisem opisu operator musi załączyć minimum jedno zdjęcie produktu. Aplikacja pokazuje miniatury zdjęć i zapisuje nazwy plików w kolumnach `image_main`, `image_template`, `image_1`, `image_2` oraz `all_images` w eksporcie XLSX/CSV.

Pierwsze zdjęcie traktuj jako główne zdjęcie PrestaShop. Drugie i kolejne zdjęcia są opcjonalne, bo część produktów ma realnie tylko jedno sensowne zdjęcie producenta.

Zdjęcia są wysyłane do Supabase Storage. W bazie i eksporcie XLSX/CSV zapisywane są ścieżki plików, np. `Partia_1/123/image/main_zdjecie.jpg`. To jest lepsze niż osadzanie obrazów w Excelu, bo PrestaShop i importery pracują na plikach, ścieżkach lub URL-ach.

Przed wysłaniem do Supabase Storage zdjęcia są automatycznie wyrównywane do kwadratowego kadru 1600 x 1600 px na białym tle, konwertowane do WebP i kompresowane. Dzięki temu operator może wgrać duże zdjęcie, a w bazie zostanie zapisana lżejsza i bardziej spójna wizualnie wersja gotowa do użycia w sklepie.

W eksporcie dostępne są zarówno ścieżki Storage, jak i URL-e:

- `image_main`, `image_template`, `image_1`, `image_2`, `all_images`,
- `image_main_url`, `image_template_url`, `image_1_url`, `image_2_url`, `all_image_urls`.

## Załączniki produktu

Operator może dodać do produktu dodatkowe załączniki z nazwą, np. instrukcję, deklarację zgodności, dodatkowy PDF producenta albo plik pomocniczy. Limit to maksymalnie 8 załączników na produkt.

Załączniki są zapisywane w Supabase Storage jako assety produktu z typem `attachment`. Eksport XLSX/CSV zawiera zbiorcze kolumny `attachments` oraz `attachment_urls`.

## Filtry i cechy PrestaShop

AI próbuje wyciągnąć filtry/cechy produktu z karty katalogowej i pokazuje je w edytowalnej tabeli. Operator może poprawić wartości albo dopisać brakujące parametry ręcznie, ale tylko po sprawdzeniu dokumentacji.

Każdy filtr ma checkbox `Użyj w PrestaShop`. Zaznaczone filtry trafiają do kolumny `features`. Odznaczone filtry zostają zapisane w `filters_json` oraz w czytelnej kolumnie `disabled_features`, ale nie trafiają do `features`.

Filtry nie są zaznaczane automatycznie. AI może zaproponować nazwę i wartość, ale operator musi świadomie zaznaczyć `Użyj w PrestaShop`. Gdy operator wpisze nową nazwę filtra i zapisze produkt, nazwa trafia do globalnego słownika filtrów w Supabase i będzie dostępna przy kolejnych produktach.

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

Jeśli wartości nie ma w karcie katalogowej, AI ma ją pominąć i dopisać informację do brakujących danych. W XLSX filtry są zapisywane w kolumnach `filters_json`, `features` oraz `disabled_features`. CSV eksportuje pełny arkusz, żeby koordynator widział zarówno filtry aktywne, jak i odrzucone.

## Karty katalogowe w eksporcie

Karta katalogowa jest domyślnie wymagana przed zapisem produktu. Jeśli produkt nie ma osobnej karty katalogowej, operator może zaznaczyć tryb ręczny „Produkt nie ma osobnej karty katalogowej”. Wtedy AI nie generuje opisu bez źródła, a operator może zapisać ręcznie przygotowany opis bez załączania pliku.

Jeśli karta katalogowa obejmuje kilka modeli albo wariantów, opis i filtry powinny używać tylko parametrów jednoznacznie przypisanych do wybranej referencji. Nie należy podkładać karty innego produktu tylko po to, żeby wymusić generowanie opisu.

Jeśli karta jest wgrana, plik jest wysyłany do Supabase Storage, a CSV/XLSX zapisuje ścieżkę w kolumnie `catalog_file`.

Jeśli bucket jest publiczny, eksport zawiera także `catalog_url`. Jeśli bucket jest prywatny, URL może nie być bezpośrednio dostępny publicznie i do importu należy używać ścieżek Storage lub wygenerować podpisane linki w osobnym procesie.

## Supabase

Aplikacja wymaga Supabase. Bez konfiguracji Supabase nie uruchomi trybu pracy produkcyjnej.

1. Utwórz projekt w Supabase.
2. W SQL Editor uruchom plik `supabase_schema.sql` z tego repozytorium.
3. W Storage utwórz bucket:

```text
product-assets
```

Może być prywatny albo publiczny. Aplikacja zapisuje ścieżki plików w bazie; publiczny URL jest dodatkowy.

4. W Render/Streamlit/secrets ustaw:

```env
SUPABASE_URL=https://...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_STORAGE_BUCKET=product-assets
```

`SUPABASE_URL` powinien być adresem projektu, np. `https://abcxyz.supabase.co`. Jeśli przypadkiem wkleisz endpoint Data API z `/rest/v1`, aplikacja spróbuje go automatycznie obciąć do adresu projektu.

Używaj `service_role` tylko po stronie serwera. Nie publikuj tego klucza w repozytorium ani w przeglądarce.

Po aktualizacjach aplikacji możesz uruchomić `supabase_schema.sql` ponownie. Skrypt używa `create table if not exists` oraz `alter table ... add column if not exists`, więc dopisze brakujące tabele i kolumny, np. słownik filtrów, URL-e zdjęć i metadane kompresji, bez kasowania istniejących produktów.

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
APP_AUTH_SECRET=losowy_dlugi_sekret_do_zapamietania_logowania
ADMIN_PASSWORD=ustaw_haslo_admina
SUPABASE_URL=https://...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_STORAGE_BUCKET=product-assets
```

Jeśli `APP_PASSWORD` jest puste, aplikacja działa bez ekranu logowania. Przy wysyłce linku do wielu osób zalecane jest ustawienie hasła oraz użycie jednego wspólnego hasła operacyjnego albo osobnej instancji dla każdej grupy.

Po poprawnym logowaniu aplikacja dodaje podpisany parametr `auth` do adresu URL, dzięki czemu odświeżenie strony albo powrót do zakładki nie wymaga ponownego wpisywania hasła. Ustaw `APP_AUTH_SECRET` na losowy długi sekret, żeby token logowania był stabilny między restartami deployu.

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
APP_AUTH_SECRET = "losowy_dlugi_sekret_do_zapamietania_logowania"
ADMIN_PASSWORD = "ustaw_haslo_admina"
SUPABASE_URL = "https://..."
SUPABASE_SERVICE_ROLE_KEY = "..."
SUPABASE_STORAGE_BUCKET = "product-assets"
```

### Render

Możesz użyć `Procfile` albo wdrożenia Docker. W zmiennych środowiskowych ustaw `LLM_PROVIDER` oraz odpowiednie klucze API.

## Bezpieczeństwo danych i kosztów

Aplikacja nie wysyła całego Excela do LLM. Do providera trafiają tylko:

- nazwa wybranego produktu,
- referencja,
- tekst wgranej karty katalogowej.

Długie karty katalogowe są skracane do 80 000 znaków przed wysłaniem do LLM. Pliki kart i zdjęć są zapisywane w Supabase Storage, a tekst karty katalogowej może być zapisany w bazie do audytu i ponownego podglądu.

## Ograniczenia pierwszej wersji

- PDF-y skanowane nie są rozpoznawane przez OCR.
- Formatowanie oryginalnego Excela nie jest zachowywane przy eksporcie z Supabase.
- Import do PrestaShop należy wykonać dopiero po ręcznej kontroli wygenerowanych opisów.
