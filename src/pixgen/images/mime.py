"""Map image MIME types to canonical filename extensions."""

__all__: list[str] = [
    "MIME_TO_EXTENSION",
]

MIME_TO_EXTENSION: dict[str, str] = {
    "image/avif": "avif",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
