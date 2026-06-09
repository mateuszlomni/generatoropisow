from __future__ import annotations

import os
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from urllib.parse import urlparse, urlunparse

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

from services.excel_service import get_product_sheets, load_workbook_from_upload, read_sheet_to_dataframe
from services.product_filters import (
    filters_to_disabled_text,
    filters_to_features_text,
    normalize_filters,
)


class SupabaseService:
    """Persistence layer for products, statuses and file assets."""

    def __init__(self) -> None:
        load_dotenv()
        url = _normalize_supabase_url(os.getenv("SUPABASE_URL", "").strip())
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        self.bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "product-assets").strip()

        if not url or not key:
            raise ValueError(
                "Brak konfiguracji Supabase. Ustaw SUPABASE_URL, "
                "SUPABASE_SERVICE_ROLE_KEY i SUPABASE_STORAGE_BUCKET."
            )

        self.client: Client = create_client(url, key)

    def list_batches(self) -> list[dict[str, Any]]:
        response = (
            self.client.table("product_batches")
            .select("id,name,source_file_name,created_at")
            .order("name")
            .execute()
        )
        return response.data or []

    def import_excel(self, uploaded_excel) -> dict[str, int]:
        """Import all product sheets from XLSX into Supabase without deleting existing work."""
        excel_bytes = uploaded_excel.getvalue()
        workbook = load_workbook_from_upload(BytesIO(excel_bytes))
        sheet_names = get_product_sheets(workbook)
        imported: dict[str, int] = {}

        for sheet_name in sheet_names:
            df = read_sheet_to_dataframe(excel_bytes, sheet_name)
            if "id_product" not in df.columns:
                continue
            batch = self._get_or_create_batch(sheet_name, uploaded_excel.name)
            imported[sheet_name] = self._upsert_products_for_batch(batch["id"], df)

        return imported

    def list_products(self, batch_id: str, status_filter: str = "all") -> list[dict[str, Any]]:
        query = (
            self.client.table("products")
            .select("*")
            .eq("batch_id", batch_id)
            .order("id_product")
        )
        if status_filter != "all":
            query = query.eq("status", status_filter)
        response = query.execute()
        return response.data or []

    def get_product(self, product_id: str) -> dict[str, Any]:
        response = self.client.table("products").select("*").eq("id", product_id).single().execute()
        return response.data or {}

    def get_product_assets(self, product_id: str) -> list[dict[str, Any]]:
        response = (
            self.client.table("product_assets")
            .select("*")
            .eq("product_id", product_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []

    def save_product_work(
        self,
        *,
        product: dict[str, Any],
        description_short: str,
        description: str,
        filters: list[dict[str, Any]],
        operator: str,
        images: list[dict[str, Any]],
        catalog: dict[str, Any],
    ) -> dict[str, Any]:
        """Upload assets and save final operator-approved product data."""
        product_uuid = product["id"]
        batch_name = product.get("batch_name") or self._batch_name(product.get("batch_id", ""))
        id_product = str(product.get("id_product", "")).strip()

        image_paths: list[str] = []
        for index, image in enumerate(images, start=1):
            role = "main" if index == 1 else ("template" if index == 2 else f"extra_{index}")
            path = self.upload_asset(
                product_id=product_uuid,
                batch_name=batch_name,
                id_product=id_product,
                asset_type="image",
                role=role,
                file_name=image["name"],
                file_bytes=image["bytes"],
                content_type=image.get("type", ""),
            )
            image_paths.append(path)

        catalog_path = self.upload_asset(
            product_id=product_uuid,
            batch_name=batch_name,
            id_product=id_product,
            asset_type="catalog",
            role="catalog",
            file_name=catalog["name"],
            file_bytes=catalog["bytes"],
            content_type=catalog.get("type", ""),
        )

        normalized_filters = normalize_filters(filters)
        update_payload = {
            "description_short": description_short,
            "description": description,
            "filters_json": normalized_filters,
            "features": filters_to_features_text(normalized_filters),
            "disabled_features": filters_to_disabled_text(normalized_filters),
            "image_main": image_paths[0] if len(image_paths) >= 1 else "",
            "image_template": image_paths[1] if len(image_paths) >= 2 else "",
            "image_1": image_paths[0] if len(image_paths) >= 1 else "",
            "image_2": image_paths[1] if len(image_paths) >= 2 else "",
            "all_images": " | ".join(image_paths),
            "catalog_file": catalog_path,
            "catalog_text": catalog.get("text", ""),
            "operator": operator,
            "status": "done",
            "updated_at": datetime.now(UTC).isoformat(),
        }

        response = (
            self.client.table("products")
            .update(update_payload)
            .eq("id", product_uuid)
            .execute()
        )
        return (response.data or [{}])[0]

    def upload_asset(
        self,
        *,
        product_id: str,
        batch_name: str,
        id_product: str,
        asset_type: str,
        role: str,
        file_name: str,
        file_bytes: bytes,
        content_type: str = "",
    ) -> str:
        """Upload one file to Supabase Storage and register it in product_assets."""
        storage_path = "/".join(
            [
                _safe_path_part(batch_name),
                _safe_path_part(id_product),
                asset_type,
                f"{role}_{_safe_file_name(file_name)}",
            ]
        )

        bucket = self.client.storage.from_(self.bucket)
        try:
            bucket.remove([storage_path])
        except Exception:
            pass
        bucket.upload(
            storage_path,
            file_bytes,
            {"content-type": content_type or "application/octet-stream"},
        )

        public_url = ""
        try:
            public_url = bucket.get_public_url(storage_path)
        except Exception:
            public_url = ""

        self.client.table("product_assets").insert(
            {
                "product_id": product_id,
                "asset_type": asset_type,
                "role": role,
                "file_name": file_name,
                "storage_path": storage_path,
                "public_url": public_url,
                "content_type": content_type,
            }
        ).execute()
        return storage_path

    def export_products_dataframe(self, batch_id: str | None = None) -> pd.DataFrame:
        query = self.client.table("products").select("*").order("id_product")
        if batch_id:
            query = query.eq("batch_id", batch_id)
        products = query.execute().data or []
        return pd.DataFrame(products).fillna("")

    def _get_or_create_batch(self, name: str, source_file_name: str) -> dict[str, Any]:
        existing = self.client.table("product_batches").select("*").eq("name", name).execute().data or []
        if existing:
            return existing[0]
        response = (
            self.client.table("product_batches")
            .insert({"name": name, "source_file_name": source_file_name})
            .execute()
        )
        return response.data[0]

    def _upsert_products_for_batch(self, batch_id: str, df: pd.DataFrame) -> int:
        existing = (
            self.client.table("products")
            .select("id_product")
            .eq("batch_id", batch_id)
            .execute()
            .data
            or []
        )
        existing_ids = {str(row["id_product"]).strip() for row in existing}
        records: list[dict[str, Any]] = []

        prepared = df.fillna("")
        for _, row in prepared.iterrows():
            id_product = str(row.get("id_product", "")).strip()
            if not id_product or id_product in existing_ids:
                continue
            records.append(
                {
                    "batch_id": batch_id,
                    "id_product": id_product,
                    "product_name": str(row.get("product_name", "")).strip(),
                    "reference": str(row.get("reference", "")).strip(),
                    "description": str(row.get("description", "")).strip(),
                    "description_short": str(row.get("description_short", "")).strip(),
                    "status": "todo",
                }
            )

        if records:
            self.client.table("products").insert(records).execute()
        return len(records)

    def _batch_name(self, batch_id: str) -> str:
        if not batch_id:
            return "batch"
        response = self.client.table("product_batches").select("name").eq("id", batch_id).single().execute()
        return str((response.data or {}).get("name", "batch"))


def _safe_path_part(value: str) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in str(value))
    return "_".join(part for part in cleaned.split("_") if part) or "item"


def _safe_file_name(value: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    cleaned = "".join(character if character in allowed else "_" for character in str(value))
    return cleaned.strip("._") or "file"


def _normalize_supabase_url(value: str) -> str:
    """Accept either the project URL or copied REST endpoint and return the project URL."""
    if not value:
        return ""
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return value.strip().rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")
