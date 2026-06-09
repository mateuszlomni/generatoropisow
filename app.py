from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
from html import escape
from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from llm.factory import get_llm_provider
from services.description_generator import CATALOG_TEXT_LIMIT, generate_product_description
from services.document_reader import read_catalog_file
from services.prestashop_export import export_prestashop_csv
from services.product_filters import default_filter_rows, filters_from_json, normalize_filters
from services.supabase_service import SupabaseService
from services.validators import validate_html

load_dotenv()

ENV_KEYS = (
    "LLM_PROVIDER",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "APP_PASSWORD",
    "APP_AUTH_SECRET",
    "ADMIN_PASSWORD",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_STORAGE_BUCKET",
)

STATUS_LABELS = {
    "all": "wszystkie",
    "todo": "do uzupełnienia",
    "done": "uzupełnione",
}

APP_CSS = """
<style>
div[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px 14px;
}
.guide-box {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 14px 16px;
    background: #f8fafc;
    margin: 8px 0 14px;
}
.step-row {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 7px 0;
    border-bottom: 1px solid #e5e7eb;
}
.step-row:last-child {
    border-bottom: 0;
}
.step-pill {
    min-width: 76px;
    text-align: center;
    border-radius: 999px;
    padding: 3px 8px;
    font-size: 12px;
    font-weight: 700;
}
.step-ok {
    color: #166534;
    background: #dcfce7;
}
.step-missing {
    color: #92400e;
    background: #fef3c7;
}
.product-card {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 14px 16px;
    background: #ffffff;
}
.muted-small {
    color: #64748b;
    font-size: 13px;
}
</style>
"""


def load_streamlit_secrets_to_env() -> None:
    """Expose Streamlit Cloud/host secrets as environment variables."""
    try:
        for key in ENV_KEYS:
            if not os.getenv(key) and key in st.secrets:
                os.environ[key] = str(st.secrets[key])
    except Exception:
        return


@st.cache_resource
def get_supabase_service() -> SupabaseService:
    """Create one Supabase client for the Streamlit process."""
    return SupabaseService()


def init_state() -> None:
    defaults: dict[str, Any] = {
        "authenticated": False,
        "operator_name": "",
        "selected_product_uuid": "",
        "description_short_editor": "",
        "description_editor": "",
        "filter_editor": [],
        "catalog_upload": None,
        "catalog_text": "",
        "manual_without_catalog": False,
        "image_uploads": [],
        "generated_data": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_page_style() -> None:
    """Apply small readability improvements to the Streamlit layout."""
    st.markdown(APP_CSS, unsafe_allow_html=True)


def render_access_gate() -> bool:
    password = os.getenv("APP_PASSWORD", "").strip()
    if not password:
        return True

    auth_token = st.query_params.get("auth", "")
    if _is_valid_auth_token(str(auth_token)):
        st.session_state.authenticated = True

    if st.session_state.authenticated:
        return True

    st.title("Generator opisów produktów PrestaShop")
    st.info("Podaj hasło dostępu, aby rozpocząć pracę.")
    with st.form("access_form"):
        entered_password = st.text_input("Hasło", type="password")
        submitted = st.form_submit_button("Wejdź")

    if submitted:
        if entered_password == password:
            st.session_state.authenticated = True
            st.query_params["auth"] = _auth_token()
            st.rerun()
        st.error("Nieprawidłowe hasło.")
    return False


def _auth_secret() -> str:
    return (
        os.getenv("APP_AUTH_SECRET", "").strip()
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("APP_PASSWORD", "").strip()
    )


def _auth_token() -> str:
    secret = _auth_secret().encode("utf-8")
    return hmac.new(secret, b"prestashop-generator-auth-v1", hashlib.sha256).hexdigest()


def _is_valid_auth_token(token: str) -> bool:
    if not token or not _auth_secret():
        return False
    return hmac.compare_digest(token, _auth_token())


def render_sidebar() -> None:
    provider = os.getenv("LLM_PROVIDER", "gemini")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash") if provider == "gemini" else os.getenv("OPENAI_MODEL", "")
    bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "product-assets")

    st.sidebar.header("Konfiguracja")
    st.sidebar.write(f"Provider LLM: **{provider}**")
    st.sidebar.write(f"Model: **{model or 'brak'}**")
    st.sidebar.write(f"Supabase Storage: **{bucket}**")
    st.sidebar.text_input("Operator", key="operator_name", placeholder="Imię lub inicjały")
    st.sidebar.info("Produkty, statusy, zdjęcia i karty katalogowe są zapisywane centralnie w Supabase.")
    with st.sidebar.expander("Instrukcja dla operatora", expanded=True):
        st.markdown(
            """
1. Wybierz partię i produkt.
2. Wgraj kartę katalogową albo zaznacz tryb ręczny.
3. Wgraj minimum jedno zdjęcie.
4. Wygeneruj lub wpisz opis.
5. Sprawdź filtry i zaznacz tylko pewne dane.
6. Zapisz produkt w Supabase.
"""
        )
    if os.getenv("APP_PASSWORD", "").strip() and st.sidebar.button("Wyloguj"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()


def render_admin_import(service: SupabaseService) -> None:
    """Import the master XLSX into Supabase."""
    with st.expander("Import stałego Excela do Supabase", expanded=False):
        admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
        if admin_password:
            entered = st.text_input("Hasło administratora", type="password")
            if entered != admin_password:
                st.caption("Podaj hasło administratora, aby importować plik.")
                return

        uploaded_excel = st.file_uploader("Wgraj główny plik XLSX z produktami", type=["xlsx"])
        if uploaded_excel and st.button("Importuj / dopisz produkty do bazy"):
            try:
                with st.spinner("Importuję produkty do Supabase..."):
                    result = service.import_excel(uploaded_excel)
                st.success("Import zakończony: " + ", ".join(f"{sheet}: {count}" for sheet, count in result.items()))
                st.rerun()
            except Exception as exc:
                st.error(f"Nie udało się zaimportować Excela: {exc}")


def product_label(product: dict[str, Any]) -> str:
    return f"{product.get('id_product', '')} | {product.get('reference', '')} | {product.get('product_name', '')}"


def empty_text(value: Any) -> bool:
    return str(value or "").strip() == ""


def product_is_missing_description(product: dict[str, Any]) -> bool:
    return empty_text(product.get("description")) or empty_text(product.get("description_short"))


def product_has_catalog(product: dict[str, Any]) -> bool:
    return bool(str(product.get("catalog_file", "") or "").strip() or str(product.get("catalog_text", "") or "").strip())


def product_has_image(product: dict[str, Any]) -> bool:
    return bool(str(product.get("image_main", "") or "").strip())


def get_product_readiness(product: dict[str, Any]) -> dict[str, bool]:
    """Return coarse product completion signals used by the guided UI."""
    has_description = bool(st.session_state.description_short_editor.strip() and st.session_state.description_editor.strip())
    manual_without_catalog = bool(st.session_state.manual_without_catalog)
    has_catalog = manual_without_catalog or bool(st.session_state.catalog_upload) or product_has_catalog(product)
    has_images = len(st.session_state.image_uploads) >= 1 or product_has_image(product)
    short_ok = len(st.session_state.description_short_editor.strip()) <= 500
    html_ok = True
    for html in (st.session_state.description_short_editor, st.session_state.description_editor):
        is_valid, _ = validate_html(html)
        html_ok = html_ok and (not html or is_valid)
    return {
        "has_description": has_description,
        "has_catalog": has_catalog,
        "has_images": has_images,
        "short_ok": short_ok,
        "html_ok": html_ok,
        "can_save": has_description and has_catalog and has_images and short_ok and html_ok,
    }


def render_batch_overview(products: list[dict[str, Any]]) -> None:
    """Show a compact status summary for the selected batch."""
    total = len(products)
    done = sum(1 for product in products if product.get("status") == "done")
    todo = total - done
    with_description = sum(1 for product in products if not product_is_missing_description(product))
    with_image = sum(1 for product in products if product_has_image(product))
    columns = st.columns(4)
    columns[0].metric("Produkty w widoku", total)
    columns[1].metric("Do zrobienia", todo)
    columns[2].metric("Uzupełnione", done)
    columns[3].metric("Ze zdjęciem", with_image)
    st.caption(f"Opis pełny i krótki ma {with_description} z {total} produktów w aktualnym filtrze.")


def render_operator_guide() -> None:
    st.markdown(
        """
<div class="guide-box">
<strong>Jak uzupełnić produkt</strong>
<div class="muted-small">Idź od lewej do prawej po zakładkach. AI jest pomocnikiem, ale zapis robisz dopiero po ręcznej kontroli opisu i filtrów.</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_readiness_panel(product: dict[str, Any]) -> dict[str, bool]:
    """Render the current save checklist and return readiness flags."""
    readiness = get_product_readiness(product)
    rows = [
        ("Produkt", True, "Wybrany produkt z partii."),
        ("Karta", readiness["has_catalog"], "Wgraj kartę albo zaznacz tryb ręczny, jeśli produkt nie ma własnej karty."),
        ("Zdjęcie", readiness["has_images"], "Wymagane jest minimum jedno zdjęcie główne."),
        ("Opis", readiness["has_description"], "Uzupełnij krótki i pełny opis."),
        ("HTML", readiness["short_ok"] and readiness["html_ok"], "Krótki opis do 500 znaków, bez zakazanych tagów."),
    ]
    html_rows = []
    for label, ok, text in rows:
        pill_class = "step-ok" if ok else "step-missing"
        pill_text = "Gotowe" if ok else "Brakuje"
        html_rows.append(
            f"""
<div class="step-row">
  <span class="step-pill {pill_class}">{pill_text}</span>
  <div><strong>{escape(label)}</strong><br><span class="muted-small">{escape(text)}</span></div>
</div>
"""
        )
    st.markdown(f'<div class="guide-box">{"".join(html_rows)}</div>', unsafe_allow_html=True)
    return readiness


def reset_editor_for_product(product: dict[str, Any]) -> None:
    product_uuid = str(product.get("id", ""))
    if st.session_state.selected_product_uuid == product_uuid:
        return

    st.session_state.selected_product_uuid = product_uuid
    st.session_state.description_short_editor = str(product.get("description_short", ""))
    st.session_state.description_editor = str(product.get("description", ""))
    filters = product.get("filters_json", [])
    if isinstance(filters, str):
        filters = filters_from_json(filters)
    st.session_state.filter_editor = normalize_filters(filters) or default_filter_rows(str(product.get("product_name", "")))
    st.session_state.catalog_upload = None
    st.session_state.catalog_text = str(product.get("catalog_text", ""))
    st.session_state.manual_without_catalog = False
    st.session_state.image_uploads = []
    st.session_state.generated_data = None


def render_product_table(products: list[dict[str, Any]]) -> None:
    if not products:
        st.info("Brak produktów w wybranej partii.")
        return

    table = pd.DataFrame(products)
    table["opis"] = table.apply(lambda row: "tak" if not product_is_missing_description(row.to_dict()) else "nie", axis=1)
    table["zdjęcie"] = table.apply(lambda row: "tak" if product_has_image(row.to_dict()) else "nie", axis=1)
    table["karta"] = table.apply(lambda row: "tak" if product_has_catalog(row.to_dict()) else "nie", axis=1)
    visible_columns = [
        "status",
        "id_product",
        "product_name",
        "reference",
        "opis",
        "zdjęcie",
        "karta",
        "operator",
        "updated_at",
    ]
    for column in visible_columns:
        if column not in table.columns:
            table[column] = ""
    st.dataframe(
        table[visible_columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            "status": "Status",
            "id_product": "ID",
            "product_name": "Produkt",
            "reference": "Referencja",
            "opis": "Opis",
            "zdjęcie": "Zdjęcie",
            "karta": "Karta",
            "operator": "Operator",
            "updated_at": "Ostatnia zmiana",
        },
    )


def render_product_details(product: dict[str, Any], assets: list[dict[str, Any]]) -> None:
    st.subheader("Wybrany produkt")
    st.markdown(
        f"""
<div class="product-card">
  <div class="muted-small">ID produktu</div>
  <strong>{escape(str(product.get('id_product', '')))}</strong>
  <div style="height: 8px"></div>
  <div class="muted-small">Nazwa</div>
  <strong>{escape(str(product.get('product_name', '')))}</strong>
  <div style="height: 8px"></div>
  <div class="muted-small">Referencja</div>
  <strong>{escape(str(product.get('reference', '')))}</strong>
</div>
""",
        unsafe_allow_html=True,
    )
    info_columns = st.columns(3)
    info_columns[0].metric("Status", str(product.get("status", "todo")))
    info_columns[1].metric("Opis", "tak" if not product_is_missing_description(product) else "nie")
    info_columns[2].metric("Zdjęcie", "tak" if product_has_image(product) else "nie")
    if product.get("operator"):
        st.caption(f"Ostatnio zapisał: {product.get('operator')}")

    if assets:
        with st.expander("Pliki zapisane w Supabase Storage", expanded=False):
            assets_df = pd.DataFrame(assets)
            st.dataframe(assets_df[["asset_type", "role", "file_name", "storage_path"]], use_container_width=True, hide_index=True)


def render_catalog_upload(product: dict[str, Any]) -> dict[str, Any] | None:
    st.subheader("Karta katalogowa")
    st.caption("Jeżeli karta obejmuje kilka wariantów, AI ma użyć tylko danych pasujących do wybranej referencji.")
    manual_without_catalog = st.checkbox(
        "Produkt nie ma osobnej karty katalogowej - opis uzupełniam ręcznie",
        value=bool(st.session_state.manual_without_catalog),
        key=f"manual_without_catalog_{product['id']}",
    )
    st.session_state.manual_without_catalog = manual_without_catalog
    if manual_without_catalog:
        st.info("Tryb ręczny wyłącza generowanie AI bez źródła i pozwala zapisać opis bez pliku karty.")
        st.session_state.catalog_upload = None
        return None

    uploaded = st.file_uploader(
        "Wgraj PDF, DOCX albo TXT",
        type=["pdf", "docx", "txt"],
        key=f"catalog_{product['id']}",
    )

    if uploaded is None:
        if product.get("catalog_file"):
            st.info(f"W bazie jest karta: {product['catalog_file']}")
        if st.session_state.catalog_text:
            st.text_area("Tekst zapisanej karty", value=st.session_state.catalog_text[:10_000], height=220, disabled=True)
        return None

    try:
        file_bytes = uploaded.getvalue()
        catalog_text = read_catalog_file(uploaded)
    except Exception as exc:
        st.error(f"Nie udało się odczytać karty katalogowej: {exc}")
        return None

    st.session_state.catalog_text = catalog_text
    catalog = {"name": uploaded.name, "type": uploaded.type, "bytes": file_bytes, "text": catalog_text}
    st.session_state.catalog_upload = catalog

    if len(catalog_text.strip()) < 300:
        st.warning("Odczytany tekst jest bardzo krótki. Karta może być skanem albo wymagać OCR.")
    if len(catalog_text) > CATALOG_TEXT_LIMIT:
        st.warning(f"Tekst ma {len(catalog_text):,} znaków i zostanie skrócony do {CATALOG_TEXT_LIMIT:,} znaków dla LLM.")
    st.text_area("Podgląd odczytanego tekstu", value=catalog_text[:10_000], height=260, disabled=True)
    return catalog


def render_image_upload(product: dict[str, Any]) -> list[dict[str, Any]]:
    st.subheader("Zdjęcia produktu")
    uploaded_images = st.file_uploader(
        "Załącz minimum 1 zdjęcie: pierwsze będzie zdjęciem głównym PrestaShop",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key=f"images_{product['id']}",
    )

    images: list[dict[str, Any]] = []
    for uploaded in uploaded_images or []:
        images.append({"name": uploaded.name, "type": uploaded.type, "bytes": uploaded.getvalue()})
    st.session_state.image_uploads = images

    if len(images) < 1 and not product.get("image_main"):
        st.warning("Do zapisu wymagane jest co najmniej 1 zdjęcie produktu.")
    elif images:
        st.success(f"Załączono {len(images)} zdjęcia/zdjęć.")

    if images:
        original_total = sum(len(image["bytes"]) for image in images)
        st.caption(
            "Zdjęcia zostaną wyrównane do kwadratowego kadru i przekonwertowane do WebP przed zapisem. "
            f"Łączny rozmiar wejściowy: {original_total / 1024 / 1024:.2f} MB."
        )
        columns = st.columns(min(len(images), 4))
        for index, image in enumerate(images[:4]):
            role = "Główne PrestaShop" if index == 0 else "Dodatkowe / szablon"
            with columns[index % len(columns)]:
                st.image(image["bytes"], caption=f"{role}: {image['name']}", use_container_width=True)

    return images


def render_generation(product: dict[str, Any]) -> None:
    st.subheader("Generowanie i edycja opisu")
    catalog_text = st.session_state.catalog_text
    can_generate = bool(catalog_text.strip()) and not st.session_state.manual_without_catalog
    if st.session_state.manual_without_catalog:
        st.info("Tryb ręczny bez karty katalogowej: generowanie AI jest wyłączone, żeby nie tworzyć opisu bez źródła.")

    if st.button("Generuj opis", disabled=not can_generate):
        try:
            with st.spinner("Generuję opis na podstawie karty katalogowej..."):
                provider = get_llm_provider()
                generated = generate_product_description(
                    provider,
                    str(product.get("product_name", "")),
                    str(product.get("reference", "")),
                    catalog_text,
                )
            st.session_state.generated_data = generated
            st.session_state.description_short_editor = generated["description_short"]
            st.session_state.description_editor = generated["description"]
            st.session_state.filter_editor = normalize_filters(generated.get("filters", [])) or st.session_state.filter_editor
            st.success("Opis wygenerowany. Sprawdź go przed zapisem.")
        except Exception as exc:
            st.error(f"Nie udało się wygenerować opisu: {exc}")

    generated_data = st.session_state.generated_data
    if generated_data:
        if generated_data.get("warnings"):
            st.warning("Ostrzeżenia: " + " | ".join(map(str, generated_data["warnings"])))
        if generated_data.get("missing_data"):
            st.info("Brakujące dane: " + " | ".join(map(str, generated_data["missing_data"])))

    st.text_area(
        "Krótki opis do PrestaShop (description_short, maks. 500 znaków)",
        key="description_short_editor",
        height=140,
    )
    st.caption(f"Znaki: {len(st.session_state.description_short_editor)} / 500")
    st.text_area("Pełny opis HTML do PrestaShop (description)", key="description_editor", height=360)

    if len(st.session_state.description_short_editor) > 500:
        st.warning("description_short przekracza 500 znaków.")

    for field_name, html in (
        ("description_short", st.session_state.description_short_editor),
        ("description", st.session_state.description_editor),
    ):
        is_valid, errors = validate_html(html)
        if html and not is_valid:
            st.error(f"{field_name}: {' '.join(errors)}")


def render_filter_editor(product: dict[str, Any]) -> list[dict[str, Any]]:
    st.subheader("Filtry i cechy produktu")
    st.caption("Dodaj filtr ręcznie albo wybierz ze słownika. Tylko zaznaczone filtry trafią do PrestaShop.")

    service = get_supabase_service()
    filter_options = service.list_filter_options()
    if filter_options:
        selected_option = st.selectbox("Dodaj filtr ze słownika", [""] + filter_options)
        if selected_option and st.button("Dodaj wybrany filtr"):
            existing_names = {str(item.get("name", "")).strip().lower() for item in st.session_state.filter_editor}
            if selected_option.lower() not in existing_names:
                st.session_state.filter_editor.append({"enabled": False, "name": selected_option, "value": "", "source": ""})
                st.rerun()

    filter_df = pd.DataFrame(st.session_state.filter_editor)
    if filter_df.empty:
        filter_df = pd.DataFrame(default_filter_rows(str(product.get("product_name", ""))))
    if "enabled" not in filter_df.columns:
        filter_df.insert(0, "enabled", False)
    if filter_df.empty:
        filter_df = pd.DataFrame(columns=["enabled", "name", "value", "source"])

    edited_df = st.data_editor(
        filter_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "enabled": st.column_config.CheckboxColumn("Użyj w PrestaShop", default=False),
            "name": st.column_config.TextColumn("Filtr / cecha"),
            "value": st.column_config.TextColumn("Wartość"),
            "source": st.column_config.TextColumn("Źródło z karty"),
        },
        key=f"filters_{product['id']}",
    )
    filters = normalize_filters(edited_df.to_dict("records"))
    st.session_state.filter_editor = filters
    return filters


def render_description_preview() -> None:
    st.subheader("Podgląd opisu")
    short_html = st.session_state.description_short_editor.strip()
    full_html = st.session_state.description_editor.strip()
    if short_html:
        st.markdown("**Krótki opis**")
        components.html(short_html, height=140, scrolling=True)
    if full_html:
        st.markdown("**Pełny opis**")
        components.html(full_html, height=520, scrolling=True)
    if not short_html and not full_html:
        st.info("Podgląd pojawi się po wygenerowaniu albo wpisaniu opisu.")


def export_dataframe_to_xlsx(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        sanitize_dataframe_for_excel(df).to_excel(writer, sheet_name="Produkty", index=False)
    return output.getvalue()


def sanitize_dataframe_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    """Remove control characters rejected by openpyxl."""
    illegal_chars = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]")
    sanitized = df.fillna("").copy()
    for column in sanitized.columns:
        sanitized[column] = sanitized[column].map(
            lambda value: illegal_chars.sub("", _excel_safe_value(value))
        )
    return sanitized


def _excel_safe_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def safe_filename_part(value: str) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value.strip())
    return "_".join(part for part in cleaned.split("_") if part) or "export"


def main() -> None:
    st.set_page_config(page_title="Generator opisów produktów PrestaShop", layout="wide")
    load_streamlit_secrets_to_env()
    init_state()
    render_page_style()

    if not render_access_gate():
        return

    try:
        service = get_supabase_service()
    except Exception as exc:
        st.error(f"Aplikacja wymaga Supabase: {exc}")
        st.stop()

    render_sidebar()
    st.title("Generator opisów produktów PrestaShop")
    st.caption("Centralna praca na produktach zapisanych w Supabase.")
    render_operator_guide()

    render_admin_import(service)

    batches = service.list_batches()
    if not batches:
        st.info("Brak partii w Supabase. Administrator musi najpierw zaimportować główny Excel.")
        return

    st.subheader("Krok 1. Wybierz partię i produkt")
    selection_columns = st.columns([2, 3])
    with selection_columns[0]:
        batch = st.selectbox("Partia", batches, format_func=lambda item: item["name"])
    with selection_columns[1]:
        status_filter = st.radio(
            "Pokaż produkty",
            list(STATUS_LABELS.keys()),
            format_func=lambda value: STATUS_LABELS[value],
            horizontal=True,
        )
    products = service.list_products(batch["id"], status_filter=status_filter)
    render_batch_overview(products)
    render_product_table(products)

    if not products:
        return

    selected_product_id = st.selectbox(
        "Produkt do uzupełnienia",
        [product["id"] for product in products],
        format_func=lambda product_id: product_label(next(product for product in products if product["id"] == product_id)),
    )
    product = service.get_product(selected_product_id)
    product["batch_name"] = batch["name"]
    reset_editor_for_product(product)
    assets = service.get_product_assets(product["id"])

    if st.button("Następny produkt do uzupełnienia"):
        todo_products = [item for item in service.list_products(batch["id"], "todo") if item["id"] != product["id"]]
        if todo_products:
            st.session_state.selected_product_uuid = ""
            st.rerun()
        else:
            st.info("Nie ma kolejnego produktu ze statusem do uzupełnienia.")

    st.divider()
    st.subheader("Krok 2. Uzupełnij produkt")
    st.info("Przejdź po zakładkach od lewej do prawej. Pełna checklista gotowości jest w zakładce „Podgląd i zapis”.")

    filters = st.session_state.filter_editor
    tabs = st.tabs(
        [
            "1. Produkt",
            "2. Materiały",
            "3. Opis",
            "4. Filtry",
            "5. Podgląd i zapis",
            "6. Eksport",
        ]
    )

    with tabs[0]:
        render_product_details(product, assets)

    with tabs[1]:
        st.info("Najpierw dodaj materiały źródłowe. Bez karty AI nie generuje opisu; bez zdjęcia nie zapiszesz produktu.")
        material_columns = st.columns([1, 1])
        with material_columns[0]:
            render_catalog_upload(product)
        with material_columns[1]:
            render_image_upload(product)

    with tabs[2]:
        st.info("Wygeneruj opis z karty albo wpisz go ręcznie. Przed zapisem przeczytaj całość i usuń dane, których nie da się potwierdzić.")
        render_generation(product)

    with tabs[3]:
        st.info("Filtry zapisują się w produkcie, ale do PrestaShop trafią tylko te zaznaczone checkboxem.")
        filters = render_filter_editor(product)

    with tabs[4]:
        render_description_preview()
        st.subheader("Zapis do Supabase")
        readiness = render_readiness_panel(product)
        manual_without_catalog = bool(st.session_state.manual_without_catalog)

        if not readiness["has_description"]:
            st.info("Opis jest wymagany przed zapisem.")
        if not readiness["has_catalog"]:
            st.info("Wgraj kartę katalogową albo zaznacz tryb ręczny dla produktu bez osobnej karty.")
        if not readiness["has_images"]:
            st.info("Minimum 1 zdjęcie jest wymagane przed zapisem.")
        if not readiness["short_ok"]:
            st.warning("Krótki opis ma ponad 500 znaków. Skróć go przed zapisem.")
        if not readiness["html_ok"]:
            st.warning("Opis zawiera niedozwolony HTML. Popraw pola opisu przed zapisem.")
        if product.get("status") == "done":
            st.caption("Produkt jest już uzupełniony. Jeśli nie wgrasz nowych plików, aplikacja zachowa istniejące zdjęcia i kartę.")

        if st.button("Zapisz produkt w Supabase", disabled=not readiness["can_save"], type="primary"):
            try:
                with st.spinner("Zapisuję opis, filtry, zdjęcia i kartę katalogową do Supabase..."):
                    service.save_product_work(
                        product=product,
                        description_short=st.session_state.description_short_editor,
                        description=st.session_state.description_editor,
                        filters=filters,
                        operator=st.session_state.operator_name.strip(),
                        images=st.session_state.image_uploads,
                        catalog=None if manual_without_catalog else st.session_state.catalog_upload,
                        manual_without_catalog=manual_without_catalog,
                    )
                st.success("Produkt zapisany w Supabase.")
                st.session_state.selected_product_uuid = ""
                st.rerun()
            except Exception as exc:
                st.error(f"Nie udało się zapisać produktu: {exc}")

    with tabs[5]:
        st.subheader("Eksport z Supabase")
        st.caption("Pobierasz aktualny stan bieżącej partii bezpośrednio z bazy.")
        export_df = service.export_products_dataframe(batch["id"])
        export_columns = st.columns(2)
        with export_columns[0]:
            st.download_button(
                "Pobierz XLSX z bieżącej partii",
                data=export_dataframe_to_xlsx(export_df),
                file_name=f"produkty_{safe_filename_part(batch['name'])}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with export_columns[1]:
            st.download_button(
                "Pobierz CSV z bieżącej partii",
                data=export_prestashop_csv(export_df),
                file_name=f"prestashop_{safe_filename_part(batch['name'])}.csv",
                mime="text/csv",
                use_container_width=True,
            )


if __name__ == "__main__":
    main()
