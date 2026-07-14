import base64
import logging
from io import BytesIO

import httpx
from django.conf import settings
from django.core.files.base import ContentFile
from openai import OpenAI

from ..models import GeneratedImage

log = logging.getLogger(__name__)


def _cap_dimensions(width, height, max_dim):
    if not width or not height:
        return max_dim, max_dim
    if width <= max_dim and height <= max_dim:
        return width, height
    scale = min(max_dim / float(width), max_dim / float(height))
    return max(64, int(width * scale)), max(64, int(height * scale))


def generate_image(image):
    """Generate or edit an image using the OpenAI image API.

    Behavior:
    - Use up to `OPENAI_IMAGE_MAX_REFERENCES` reference images (skip invalid ones).
    - Preserve the primary reference aspect ratio when product image dimensions are available.
    - Respect configurable settings: `OPENAI_IMAGE_MAX_DIMENSION`, `OPENAI_IMAGE_QUALITY`, `OPENAI_IMAGE_OUTPUT_FORMAT`.
    - Fail gracefully and record errors on the `GeneratedImage` record.
    """
    image.status = GeneratedImage.Status.PROCESSING
    image.save(update_fields=["status"])

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for image generation.")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    max_refs = getattr(settings, "OPENAI_IMAGE_MAX_REFERENCES", 5)
    max_dim = getattr(settings, "OPENAI_IMAGE_MAX_DIMENSION", 2048)
    quality = getattr(settings, "OPENAI_IMAGE_QUALITY", "high")
    out_format = getattr(settings, "OPENAI_IMAGE_OUTPUT_FORMAT", "webp")

    # try to infer primary image dimensions from the stored product data
    target_width = target_height = None
    try:
        product_images = image.job.product_data.get("images", []) if image.job.product_data else []
        primary_url = image.job.source_images[0] if image.job.source_images else None
        if primary_url:
            found = next((it for it in product_images if it.get("url") == primary_url), None)
            if found and found.get("width") and found.get("height"):
                target_width = int(found.get("width"))
                target_height = int(found.get("height"))
    except Exception:
        target_width = target_height = None

    reference_files = []
    downloaded = 0
    try:
        for index, url in enumerate(image.job.source_images[:max_refs]):
            if not url:
                continue
            try:
                response = httpx.get(url, timeout=30, follow_redirects=True)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0]
                if not content_type.startswith("image/"):
                    log.warning("Skipping non-image reference: %s", url)
                    continue
                if len(response.content) > 50 * 1024 * 1024:
                    log.warning("Skipping oversized reference (>50MB): %s", url)
                    continue
                extension = {"image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
                buf = BytesIO(response.content)
                buf.name = f"reference-{downloaded}.{extension}"
                reference_files.append(buf)
                downloaded += 1
            except Exception as exc:
                log.warning("Failed to fetch reference %s: %s", url, exc)
                continue

        # determine target size, preserve aspect ratio when possible
        if target_width and target_height:
            tw, th = _cap_dimensions(target_width, target_height, max_dim)
        else:
            # fallback to square max_dim
            tw = th = max_dim

        size_str = f"{tw}x{th}"

        arguments = {
            "model": getattr(settings, "OPENAI_IMAGE_MODEL", None),
            "prompt": image.prompt.prompt,
            "size": size_str,
            "quality": quality,
            "output_format": out_format,
        }

        try:
            result = (
                client.images.edit(image=reference_files, **arguments)
                if reference_files
                else client.images.generate(**arguments)
            )
        except Exception as exc:
            image.status = GeneratedImage.Status.FAILED
            image.error_message = f"Image generation failed: {exc}"
            image.save(update_fields=["status", "error_message"])
            log.exception("Image generation failed for image id %s", image.pk)
            return
    finally:
        for reference in reference_files:
            try:
                reference.close()
            except Exception:
                pass

    try:
        image_bytes = base64.b64decode(result.data[0].b64_json)
    except Exception as exc:
        image.status = GeneratedImage.Status.FAILED
        image.error_message = f"Failed to decode image bytes: {exc}"
        image.save(update_fields=["status", "error_message"])
        log.exception("Failed to decode generated image for id %s", image.pk)
        return

    # choose extension based on output format
    ext = "webp" if out_format == "webp" else ("png" if out_format == "png" else "jpg")
    filename = f"image-{image.pk}.{ext}"
    image.image.save(filename, ContentFile(image_bytes), save=False)
    image.status = GeneratedImage.Status.COMPLETED
    image.save(update_fields=["image", "status"])
