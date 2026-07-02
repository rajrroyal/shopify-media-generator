import base64
from io import BytesIO

import httpx
from django.conf import settings
from django.core.files.base import ContentFile
from openai import OpenAI

from ..models import GeneratedImage


def generate_image(image):
    image.status = GeneratedImage.Status.PROCESSING
    image.save(update_fields=["status"])
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for image generation.")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    reference_files = []
    try:
        for index, url in enumerate(image.job.source_images[:5]):
            response = httpx.get(url, timeout=30, follow_redirects=True)
            response.raise_for_status()
            if len(response.content) > 50 * 1024 * 1024:
                raise RuntimeError("A reference image is larger than 50 MB.")
            content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
            extension = {"image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
            buffer = BytesIO(response.content)
            buffer.name = f"reference-{index}.{extension}"
            reference_files.append(buffer)

        arguments = {
            "model": settings.OPENAI_IMAGE_MODEL,
            "prompt": image.prompt.prompt,
            "size": "1024x1024",
            "quality": "medium",
            "output_format": "webp",
        }
        result = (
            client.images.edit(image=reference_files, **arguments)
            if reference_files
            else client.images.generate(**arguments)
        )
    finally:
        for reference in reference_files:
            reference.close()
    image_bytes = base64.b64decode(result.data[0].b64_json)
    image.image.save(f"image-{image.pk}.webp", ContentFile(image_bytes), save=False)
    image.status = GeneratedImage.Status.COMPLETED
    image.save(update_fields=["image", "status"])
