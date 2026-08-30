"""Preprocess phone-photo invoices so vision models can read dense GST tables.

WhatsApp JPEGs of 19-column DMS bills are too small and too tall: the model
sees the header clearly and blurs SI 21–30. We upscale, then emit overlapping
vertical crops so later SI ranges can be read from a zoomed lower band.
"""

from __future__ import annotations

from io import BytesIO

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover — qrcode[pil] / Django installs Pillow
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]

TARGET_LONG_EDGE = 2400
MAX_VIEWS_PER_PAGE = 3


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode in ("RGBA", "P"):
        return image.convert("RGB")
    return image.convert("RGB")


def _jpeg_bytes(image: Image.Image, *, quality: int = 88) -> bytes:
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _resample_filter():
    resampling = getattr(Image, "Resampling", None)
    if resampling is not None:
        return resampling.LANCZOS
    return Image.LANCZOS


def enhance_bill_image(raw: bytes) -> Image.Image | None:
    """Decode, autocontrast, and upscale so a 19-col table is high-detail."""
    if Image is None or not raw:
        return None
    try:
        image = Image.open(BytesIO(raw))
        image.load()
    except Exception:  # noqa: BLE001 — unreadable bytes fall back to the original
        return None
    image = _to_rgb(image)
    if ImageOps is not None:
        try:
            image = ImageOps.autocontrast(image, cutoff=1)
        except Exception:  # noqa: BLE001
            pass
    width, height = image.size
    long_edge = max(width, height)
    if long_edge < TARGET_LONG_EDGE and long_edge > 0:
        scale = TARGET_LONG_EDGE / long_edge
        image = image.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            _resample_filter(),
        )
    return image


def split_bill_image(raw: bytes) -> dict[str, bytes]:
    """Full page plus overlapping top/bottom bands for tall invoice photos."""
    image = enhance_bill_image(raw)
    if image is None:
        return {"full": raw}
    width, height = image.size
    views = {"full": _jpeg_bytes(image)}
    # Phone photos of a full tax invoice are taller than they are wide.
    if height > int(width * 1.15):
        top_cut = int(height * 0.58)
        bottom_cut = int(height * 0.42)
        views["top"] = _jpeg_bytes(image.crop((0, 0, width, top_cut)))
        views["bottom"] = _jpeg_bytes(image.crop((0, bottom_cut, width, height)))
    return views


def views_for_si_range(raw_images: list[bytes], *, start: int, cache: dict | None = None) -> list[bytes]:
    """Early SI rows use the upper crop; later rows use the lower crop."""
    if cache is None:
        cache = {}
    chosen: list[bytes] = []
    for index, raw in enumerate(raw_images):
        if index not in cache:
            cache[index] = split_bill_image(raw)
        views = cache[index]
        chosen.append(views["full"])
        band = views.get("top") if start <= 15 else views.get("bottom")
        if band:
            chosen.append(band)
        if len(chosen) >= MAX_VIEWS_PER_PAGE + 1:
            break
    return chosen[:4] or list(raw_images)
