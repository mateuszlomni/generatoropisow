from __future__ import annotations

from io import StringIO

import pandas as pd


def export_prestashop_csv(df: pd.DataFrame) -> bytes:
    """Export PrestaShop import columns as semicolon-separated CSV with UTF-8 BOM."""
    export_columns = ["id_product", "description_short", "description", "features", "image_1", "image_2", "operator"]
    prepared = df.copy().fillna("")

    for column in export_columns:
        if column not in prepared.columns:
            prepared[column] = ""

    csv_buffer = StringIO()
    prepared[export_columns].to_csv(csv_buffer, index=False, sep=";")
    return csv_buffer.getvalue().encode("utf-8-sig")
