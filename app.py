from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
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
        "image_uploads": [],
        "generated_data": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


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
    st.session_state.image_uploads = []
    st.session_state.generated_data = None


def render_product_table(products: list[dict[str, Any]]) -> None:
    if not products:
        st.info("Brak produktów w wybranej partii.")
        return

    table = pd.DataFrame(products)
    visible_columns = [
        "status",
        "id_product",
        "product_name",
        "reference",
        "operator",
        "updated_at",
        "image_main",
        "catalog_file",
    ]
    for column in visible_columns:
        if column not in table.columns:
            table[column] = ""
    st.dataframe(table[visible_columns], use_container_width=True, hide_index=True)


def render_product_details(product: dict[str, Any], assets: list[dict[str, Any]]) -> None:
    st.subheader("Szczegóły produktu")
    st.write(f"**Status:** {product.get('status', 'todo')}")
    st.write(f"**id_product:** {product.get('id_product', '')}")
    st.write(f"**product_name:** {product.get('product_name', '')}")
    st.write(f"**reference:** {product.get('reference', '')}")
    if product.get("operator"):
        st.write(f"**Ostatnio zapisał:** {product.get('operator')}")

    if assets:
        st.caption("Pliki zapisane w Supabase Storage")
        assets_df = pd.DataFrame(assets)
        st.dataframe(assets_df[["asset_type", "role", "file_name", "storage_path"]], use_container_width=True, hide_index=True)


def render_catalog_upload(product: dict[str, Any]) -> dict[str, Any] | None:
    st.subheader("Karta katalogowa")
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
        "Załącz minimum 2 zdjęcia: 1) główne PrestaShop, 2) dodatkowe / szablon",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key=f"images_{product['id']}",
    )

    images: list[dict[str, Any]] = []
    for uploaded in uploaded_images or []:
        images.append({"name": uploaded.name, "type": uploaded.type, "bytes": uploaded.getvalue()})
    st.session_state.image_uploads = images

    if len(images) < 2 and not product.get("image_main"):
        st.warning("Do zapisu wymagane są co najmniej 2 zdjęcia produktu.")
    elif images:
        st.success(f"Załączono {len(images)} zdjęcia/zdjęć.")

    if images:
        original_total = sum(len(image["bytes"]) for image in images)
        st.caption(
            "Zdjęcia zostaną automatycznie przekonwertowane do WebP przed zapisem. "
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
    can_generate = bool(catalog_text.strip())

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

    st.text_area("description_short", key="description_short_editor", height=140)
    st.text_area("description", key="description_editor", height=360)

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

    render_admin_import(service)

    batches = service.list_batches()
    if not batches:
        st.info("Brak partii w Supabase. Administrator musi najpierw zaimportować główny Excel.")
        return

    batch = st.selectbox("Wybierz partię", batches, format_func=lambda item: item["name"])
    status_filter = st.radio(
        "Status produktów",
        list(STATUS_LABELS.keys()),
        format_func=lambda value: STATUS_LABELS[value],
        horizontal=True,
    )
    products = service.list_products(batch["id"], status_filter=status_filter)
    render_product_table(products)

    if not products:
        return

    selected_product_id = st.selectbox(
        "Wybierz produkt",
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

    left, right = st.columns([1, 1])
    with left:
        render_product_details(product, assets)
    with right:
        catalog = render_catalog_upload(product)
        images = render_image_upload(product)

    render_generation(product)
    filters = render_filter_editor(product)
    render_description_preview()

    st.subheader("Zapis do Supabase")
    has_description = bool(st.session_state.description_short_editor.strip() or st.session_state.description_editor.strip())
    has_catalog = bool(st.session_state.catalog_upload or product.get("catalog_file"))
    has_images = len(st.session_state.image_uploads) >= 2 or bool(product.get("image_main") and product.get("image_template"))
    can_save = has_description and bool(st.session_state.catalog_upload) and len(st.session_state.image_uploads) >= 2

    if not has_description:
        st.info("Opis jest wymagany przed zapisem.")
    if not has_catalog:
        st.info("Karta katalogowa jest wymagana przed zapisem.")
    if not has_images:
        st.info("Minimum 2 zdjęcia są wymagane przed zapisem.")
    if product.get("status") == "done":
        st.caption("Produkt jest już uzupełniony. Ponowny zapis wymaga ponownego wgrania karty i zdjęć, żeby zachować pełny audyt plików.")

    if st.button("Zapisz produkt w Supabase", disabled=not can_save):
        try:
            with st.spinner("Zapisuję opis, filtry, zdjęcia i kartę katalogową do Supabase..."):
                service.save_product_work(
                    product=product,
                    description_short=st.session_state.description_short_editor,
                    description=st.session_state.description_editor,
                    filters=filters,
                    operator=st.session_state.operator_name.strip(),
                    images=st.session_state.image_uploads,
                    catalog=st.session_state.catalog_upload,
                )
            st.success("Produkt zapisany w Supabase.")
            st.session_state.selected_product_uuid = ""
            st.rerun()
        except Exception as exc:
            st.error(f"Nie udało się zapisać produktu: {exc}")

    st.subheader("Eksport z Supabase")
    export_df = service.export_products_dataframe(batch["id"])
    st.download_button(
        "Pobierz XLSX z bieżącej partii",
        data=export_dataframe_to_xlsx(export_df),
        file_name=f"produkty_{safe_filename_part(batch['name'])}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        "Pobierz CSV z bieżącej partii",
        data=export_prestashop_csv(export_df),
        file_name=f"prestashop_{safe_filename_part(batch['name'])}.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
