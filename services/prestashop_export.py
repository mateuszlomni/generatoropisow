from __future__ import annotations

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
        "image_1",
        "image_2",
        "all_images",
        "catalog_file",
        "operator",
    ]
    prepared = df.copy().fillna("")

    for column in preferred_columns:
        if column not in prepared.columns:
            prepared[column] = ""

    export_columns = preferred_columns + [column for column in prepared.columns if column not in preferred_columns]

    csv_buffer = StringIO()
    prepared[export_columns].to_csv(csv_buffer, index=False, sep=";")
    return csv_buffer.getvalue().encode("utf-8-sig")
