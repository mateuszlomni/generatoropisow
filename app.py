from __future__ import annotations

import os
from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from llm.factory import get_llm_provider
from services.description_generator import CATALOG_TEXT_LIMIT, generate_product_description
from services.document_reader import read_catalog_file
from services.excel_service import (
    get_product_sheets,
    load_workbook_from_upload,
    read_sheet_to_dataframe,
    update_product_description,
    write_updated_excel,
)
from services.prestashop_export import export_prestashop_csv
from services.validators import validate_html

load_dotenv()

FILTER_ALL = "wszystkie"
FILTER_NO_DESCRIPTION = "tylko bez opisu"
FILTER_EMPTY_DESCRIPTION = "tylko z pustym description"
FILTER_EMPTY_SHORT = "tylko z pustym description_short"


def init_state() -> None:
    """Initialize Streamlit session state keys used by the app."""
    defaults: dict[str, Any] = {
        "excel_name": "",
        "excel_bytes": None,
        "product_sheets": [],
        "sheet_dfs": {},
        "updated_sheets": {},
        "selected_product_id": None,
        "catalog_text": "",
        "catalog_file_key": "",
        "generated_data": None,
        "description_short_editor": "",
        "description_editor": "",
        "product_images": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def empty_text(value: Any) -> bool:
    """Return True when a spreadsheet cell should be treated as empty."""
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip() == ""


def apply_filter(df: pd.DataFrame, filter_mode: str) -> pd.DataFrame:
    """Filter products according to description completeness."""
    prepared = df.copy().fillna("")
    for column in ("description", "description_short"):
        if column not in prepared.columns:
            prepared[column] = ""

    if filter_mode == FILTER_EMPTY_DESCRIPTION:
        return prepared[prepared["description"].apply(empty_text)]
    if filter_mode == FILTER_EMPTY_SHORT:
        return prepared[prepared["description_short"].apply(empty_text)]
    if filter_mode == FILTER_NO_DESCRIPTION:
        return prepared[
            prepared["description"].apply(empty_text) | prepared["description_short"].apply(empty_text)
        ]
    return prepared


def load_excel(uploaded_excel) -> None:
    """Load workbook metadata and product sheets into session state."""
    excel_bytes = uploaded_excel.getvalue()
    workbook = load_workbook_from_upload(BytesIO(excel_bytes))
    product_sheets = get_product_sheets(workbook)
    sheet_dfs = {
        sheet_name: read_sheet_to_dataframe(excel_bytes, sheet_name=sheet_name)
        for sheet_name in product_sheets
    }

    st.session_state.excel_name = uploaded_excel.name
    st.session_state.excel_bytes = excel_bytes
    st.session_state.product_sheets = product_sheets
    st.session_state.sheet_dfs = sheet_dfs
    st.session_state.updated_sheets = {}
    st.session_state.selected_product_id = None
    st.session_state.catalog_text = ""
    st.session_state.catalog_file_key = ""
    st.session_state.generated_data = None
    st.session_state.description_short_editor = ""
    st.session_state.description_editor = ""
    st.session_state.product_images = {}


def product_label(row: pd.Series) -> str:
    """Build a readable selectbox label for one product row."""
    product_id = row.get("id_product", "")
    reference = row.get("reference", "")
    product_name = row.get("product_name", "")
    return f"{product_id} | {reference} | {product_name}"


def get_selected_product(filtered_df: pd.DataFrame) -> pd.Series | None:
    """Render product selector and return the selected row."""
    if filtered_df.empty:
        st.info("Brak produktów spełniających wybrany filtr.")
        return None

    rows = list(filtered_df.iterrows())
    ids = [str(row.get("id_product", "")).strip() for _, row in rows]
    selected_id = st.session_state.get("selected_product_id")
    default_index = ids.index(str(selected_id)) if selected_id is not None and str(selected_id) in ids else 0

    selected_position = st.selectbox(
        "Wybierz produkt",
        options=list(range(len(rows))),
        index=default_index,
        format_func=lambda position: product_label(rows[position][1]),
    )
    selected_row = rows[selected_position][1]
    st.session_state.selected_product_id = str(selected_row.get("id_product", "")).strip()
    return selected_row


def set_next_product_without_description(df: pd.DataFrame, current_id: str | None) -> None:
    """Move selection to the next product missing either description field."""
    prepared = df.copy().fillna("")
    for column in ("description", "description_short"):
        if column not in prepared.columns:
            prepared[column] = ""

    missing_mask = prepared["description"].apply(empty_text) | prepared["description_short"].apply(empty_text)
    missing_df = prepared[missing_mask]
    if missing_df.empty:
        st.info("Nie znaleziono kolejnego produktu bez opisu w tej partii.")
        return

    ids = prepared["id_product"].astype(str).str.strip().tolist()
    current_position = ids.index(str(current_id)) if current_id is not None and str(current_id) in ids else -1

    for _, row in missing_df.iterrows():
        row_id = str(row.get("id_product", "")).strip()
        if ids.index(row_id) > current_position:
            st.session_state.selected_product_id = row_id
            st.session_state.generated_data = None
            st.session_state.description_short_editor = ""
            st.session_state.description_editor = ""
            st.rerun()

    first_id = str(missing_df.iloc[0].get("id_product", "")).strip()
    st.session_state.selected_product_id = first_id
    st.session_state.generated_data = None
    st.session_state.description_short_editor = ""
    st.session_state.description_editor = ""
    st.rerun()


def render_sidebar() -> None:
    """Render provider and safety information."""
    provider = os.getenv("LLM_PROVIDER", "gemini")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash") if provider == "gemini" else os.getenv("OPENAI_MODEL", "")

    st.sidebar.header("Konfiguracja")
    st.sidebar.write(f"Provider LLM: **{provider}**")
    st.sidebar.write(f"Model: **{model or 'brak'}**")
    st.sidebar.info("Opis generowany wyłącznie na podstawie karty katalogowej.")
    st.sidebar.caption("Do LLM trafia tylko nazwa wybranego produktu, referencja i tekst wgranej karty.")


def render_product_details(product: pd.Series) -> None:
    """Show the currently selected product data."""
    st.subheader("Szczegóły produktu")
    st.write(f"**id_product:** {product.get('id_product', '')}")
    st.write(f"**product_name:** {product.get('product_name', '')}")
    st.write(f"**reference:** {product.get('reference', '')}")

    st.text_area("Aktualny description_short", value=str(product.get("description_short", "")), height=120, disabled=True)
    st.text_area("Aktualny description", value=str(product.get("description", "")), height=220, disabled=True)


def get_product_id(product: pd.Series) -> str:
    """Return a stable product id from the selected row."""
    return str(product.get("id_product", "")).strip()


def render_image_upload(product: pd.Series) -> list[dict[str, Any]]:
    """Require and preview at least two product images for the selected product."""
    product_id = get_product_id(product)
    st.subheader("Zdjęcia produktu")
    image_files = st.file_uploader(
        "Załącz minimum 2 zdjęcia produktu",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key=f"product_images_upload_{product_id}",
    )

    images: list[dict[str, Any]] = []
    for image_file in image_files or []:
        images.append(
            {
                "name": image_file.name,
                "type": image_file.type,
                "bytes": image_file.getvalue(),
            }
        )

    if images:
        st.session_state.product_images[product_id] = images
    else:
        images = st.session_state.product_images.get(product_id, [])

    if len(images) < 2:
        st.warning("Do zapisu wymagane są co najmniej 2 zdjęcia produktu.")
    else:
        st.success(f"Załączono {len(images)} zdjęcia/zdjęć.")

    if images:
        preview_columns = st.columns(min(len(images), 4))
        for index, image in enumerate(images[:4]):
            with preview_columns[index % len(preview_columns)]:
                st.image(image["bytes"], caption=image["name"], use_container_width=True)

    return images


def render_catalog_upload() -> str:
    """Upload and preview a catalog file, returning extracted text."""
    st.subheader("Karta katalogowa")
    catalog_file = st.file_uploader("Wgraj PDF, DOCX albo TXT", type=["pdf", "docx", "txt"])

    if catalog_file is None:
        st.session_state.catalog_text = ""
        st.session_state.catalog_file_key = ""
        st.info("Wgraj kartę katalogową, aby wygenerować opis.")
        return ""

    file_key = f"{catalog_file.name}:{catalog_file.size}"
    if st.session_state.catalog_file_key != file_key:
        try:
            st.session_state.catalog_text = read_catalog_file(catalog_file)
            st.session_state.catalog_file_key = file_key
        except Exception as exc:
            st.session_state.catalog_text = ""
            st.error(f"Nie udało się odczytać karty katalogowej: {exc}")
            return ""

    catalog_text = st.session_state.catalog_text
    if len(catalog_text.strip()) < 300:
        st.warning("Odczytany tekst jest bardzo krótki. Karta może być skanem albo wymagać lepszego źródła danych.")
    if len(catalog_text) > CATALOG_TEXT_LIMIT:
        st.warning(f"Tekst ma {len(catalog_text):,} znaków i zostanie skrócony do {CATALOG_TEXT_LIMIT:,} znaków dla LLM.")

    st.text_area("Podgląd odczytanego tekstu", value=catalog_text[:10_000], height=260, disabled=True)
    return catalog_text


def render_generation(product: pd.Series, catalog_text: str) -> None:
    """Render generation controls and editable generated fields."""
    st.subheader("Generowanie i edycja opisu")

    can_generate = bool(catalog_text.strip())
    if st.button("Generuj opis", disabled=not can_generate):
        product_name = str(product.get("product_name", "")).strip()
        reference = str(product.get("reference", "")).strip()
        try:
            with st.spinner("Generuję opis na podstawie karty katalogowej..."):
                provider = get_llm_provider()
                generated = generate_product_description(provider, product_name, reference, catalog_text)
            st.session_state.generated_data = generated
            st.session_state.description_short_editor = generated["description_short"]
            st.session_state.description_editor = generated["description"]
            st.success("Opis został wygenerowany. Sprawdź i popraw go przed zapisem.")
        except Exception as exc:
            st.error(f"Nie udało się wygenerować opisu: {exc}")

    generated_data = st.session_state.get("generated_data")
    if generated_data:
        warnings = generated_data.get("warnings", [])
        missing_data = generated_data.get("missing_data", [])
        if warnings:
            st.warning("Ostrzeżenia: " + " | ".join(map(str, warnings)))
        if missing_data:
            st.info("Brakujące dane: " + " | ".join(map(str, missing_data)))

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


def render_description_preview() -> None:
    """Render an HTML preview of the editable description fields."""
    st.subheader("Podgląd opisu")
    short_html = st.session_state.description_short_editor.strip()
    full_html = st.session_state.description_editor.strip()

    if not short_html and not full_html:
        st.info("Podgląd pojawi się po wygenerowaniu albo wpisaniu opisu.")
        return

    if short_html:
        st.markdown("**Krótki opis**")
        components.html(short_html, height=140, scrolling=True)

    if full_html:
        st.markdown("**Pełny opis**")
        components.html(full_html, height=520, scrolling=True)


def main() -> None:
    st.set_page_config(page_title="Generator opisów produktów PrestaShop", layout="wide")
    init_state()
    render_sidebar()

    st.title("Generator opisów produktów PrestaShop")
    st.caption("Półautomatyczne uzupełnianie opisów na podstawie kart katalogowych producenta.")

    uploaded_excel = st.file_uploader("Wgraj plik Excel z produktami", type=["xlsx"])
    if uploaded_excel is None:
        st.info("Wgraj plik XLSX, aby rozpocząć pracę.")
        return

    incoming_key = f"{uploaded_excel.name}:{uploaded_excel.size}"
    if st.session_state.excel_name != incoming_key:
        try:
            load_excel(uploaded_excel)
            st.session_state.excel_name = incoming_key
            st.success("Plik Excel został wczytany.")
        except Exception as exc:
            st.error(f"Nie udało się wczytać Excela: {exc}")
            return

    product_sheets = st.session_state.product_sheets
    if not product_sheets:
        st.error("Nie znaleziono arkuszy produktów. Arkusz 'Podsumowanie' jest ignorowany.")
        return

    selected_sheet = st.selectbox("Wybierz arkusz / partię", product_sheets)
    current_df = st.session_state.sheet_dfs[selected_sheet].fillna("")

    filter_mode = st.radio(
        "Filtr produktów",
        [FILTER_ALL, FILTER_NO_DESCRIPTION, FILTER_EMPTY_DESCRIPTION, FILTER_EMPTY_SHORT],
        horizontal=True,
    )
    filtered_df = apply_filter(current_df, filter_mode)

    st.subheader("Produkty w wybranej partii")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)

    selected_product = get_selected_product(filtered_df)
    if selected_product is None:
        return

    if st.button("Następny produkt bez opisu"):
        set_next_product_without_description(current_df, st.session_state.selected_product_id)

    left, right = st.columns([1, 1])
    with left:
        render_product_details(selected_product)
    with right:
        catalog_text = render_catalog_upload()
        selected_images = render_image_upload(selected_product)

    render_generation(selected_product, catalog_text)
    render_description_preview()

    st.subheader("Zapis i eksport")
    has_description = bool(st.session_state.description_short_editor.strip() or st.session_state.description_editor.strip())
    has_required_images = len(selected_images) >= 2
    can_save = has_description and has_required_images
    if not has_required_images:
        st.info("Zapis do Excela będzie dostępny po załączeniu minimum 2 zdjęć produktu.")
    if st.button("Zapisz opis do Excela", disabled=not can_save):
        try:
            updated_df = update_product_description(
                current_df,
                selected_product.get("id_product", ""),
                st.session_state.description_short_editor,
                st.session_state.description_editor,
            )
            for column in ("image_1", "image_2"):
                if column not in updated_df.columns:
                    updated_df[column] = ""

            product_id = get_product_id(selected_product)
            product_mask = updated_df["id_product"].astype(str).str.strip() == product_id
            updated_df.loc[product_mask, "image_1"] = selected_images[0]["name"]
            updated_df.loc[product_mask, "image_2"] = selected_images[1]["name"]

            st.session_state.sheet_dfs[selected_sheet] = updated_df
            st.session_state.updated_sheets[selected_sheet] = updated_df
            st.success("Opis został zapisany w pamięci aplikacji. Pobierz zaktualizowany XLSX, aby zachować zmiany.")
            st.rerun()
        except Exception as exc:
            st.error(f"Nie udało się zapisać opisu: {exc}")

    if st.session_state.updated_sheets:
        updated_excel = write_updated_excel(st.session_state.excel_bytes, st.session_state.updated_sheets)
        st.download_button(
            "Pobierz zaktualizowany plik XLSX",
            data=updated_excel,
            file_name="produkty_z_opisami.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    csv_bytes = export_prestashop_csv(st.session_state.sheet_dfs[selected_sheet])
    st.download_button(
        "Pobierz CSV do importu PrestaShop dla wybranej partii",
        data=csv_bytes,
        file_name=f"prestashop_{selected_sheet}.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
