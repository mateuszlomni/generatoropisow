from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

DEFAULT_MAX_IMAGE_DIMENSION = 1600
DEFAULT_WEBP_QUALITY = 82


def optimize_image_to_webp(
    image: dict[str, Any],
    *,
    max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION,
    quality: int = DEFAULT_WEBP_QUALITY,
) -> dict[str, Any]:
    """Convert an uploaded image to optimized WebP bytes."""
    original_bytes = image["bytes"]
    original_name = str(image.get("name", "image")).strip() or "image"

    with Image.open(BytesIO(original_bytes)) as source:
        source = ImageOps.exif_transpose(source)
        if source.mode not in ("RGB", "RGBA"):
            source = source.convert("RGB")

        width, height = source.size
        if max(width, height) > max_dimension:
            source.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        output = BytesIO()
        save_kwargs: dict[str, Any] = {
            "format": "WEBP",
            "quality": quality,
            "method": 6,
        }
        if source.mode == "RGBA":
            save_kwargs["lossless"] = False

        source.save(output, **save_kwargs)

    optimized_bytes = output.getvalue()
    return {
        "name": _webp_name(original_name),
        "type": "image/webp",
        "bytes": optimized_bytes,
        "original_name": original_name,
        "original_size": len(original_bytes),
        "optimized_size": len(optimized_bytes),
    }


def _webp_name(file_name: str) -> str:
    stem = Path(file_name).stem or "image"
    return f"{stem}.webp"
