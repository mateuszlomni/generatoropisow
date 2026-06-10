from __future__ import annotations

import re
from io import StringIO

import pandas as pd


def export_prestashop_csv(df: pd.DataFrame) -> bytes:
    """Export the full working sheet as semicolon-separated CSV with UTF-8 BOM."""
    preferred_columns = [
        "id_product",
        "product_name",
        "reference",
        "description_short",
        "description",
        "features",
        "disabled_features",
        "filters_json",
        "image_main",
        "image_template",
        "image_main_url",
        "image_template_url",
        "image_1",
        "image_2",
        "image_1_url",
        "image_2_url",
        "all_images",
        "all_image_urls",
        "catalog_file",
        "catalog_url",
        "attachments",
        "attachment_urls",
        "operator",
    ]
    prepared = _sanitize_for_csv(df.copy().fillna(""))

    for column in preferred_columns:
        if column not in prepared.columns:
            prepared[column] = ""

    export_columns = preferred_columns + [column for column in prepared.columns if column not in preferred_columns]

    csv_buffer = StringIO()
    prepared[export_columns].to_csv(csv_buffer, index=False, sep=";")
    return csv_buffer.getvalue().encode("utf-8-sig")


def _sanitize_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    illegal_chars = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]")
    for column in df.columns:
        df[column] = df[column].map(lambda value: illegal_chars.sub("", str(value)) if isinstance(value, str) else value)
    return df
