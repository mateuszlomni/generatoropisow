from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


def build_export_package(
    *,
    excel_bytes: bytes,
    csv_bytes: bytes,
    images_by_product: dict[str, list[dict]],
    catalogs_by_product: dict[str, dict],
) -> bytes:
    """Build a ZIP package containing XLSX, CSV, uploaded images and catalog files."""
    output = BytesIO()
    used_names: set[str] = set()

    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("produkty_z_opisami.xlsx", excel_bytes)
        archive.writestr("prestashop.csv", csv_bytes)

        for product_id, images in images_by_product.items():
            for index, image in enumerate(images, start=1):
                name = str(image.get("name", f"image_{index}")).strip() or f"image_{index}"
                arcname = _unique_name(f"images/{_safe_part(product_id)}_{index}_{_safe_name(name)}", used_names)
                archive.writestr(arcname, image.get("bytes", b""))

        for product_id, catalog in catalogs_by_product.items():
            name = str(catalog.get("name", "catalog")).strip() or "catalog"
            arcname = _unique_name(f"catalogs/{_safe_part(product_id)}_{_safe_name(name)}", used_names)
            archive.writestr(arcname, catalog.get("bytes", b""))

    return output.getvalue()


def _safe_part(value: str) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in str(value))
    return "_".join(part for part in cleaned.split("_") if part) or "product"


def _safe_name(value: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    cleaned = "".join(character if character in allowed else "_" for character in value)
    return cleaned.strip("._") or "file"


def _unique_name(name: str, used_names: set[str]) -> str:
    if name not in used_names:
        used_names.add(name)
        return name

    if "." in name.rsplit("/", 1)[-1]:
        prefix, suffix = name.rsplit(".", 1)
        suffix = f".{suffix}"
    else:
        prefix, suffix = name, ""

    counter = 2
    while True:
        candidate = f"{prefix}_{counter}{suffix}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        counter += 1
