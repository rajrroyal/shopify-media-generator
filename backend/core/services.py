import base64
import hashlib
import hmac
import json
import secrets
from io import BytesIO
from urllib.parse import urlencode

import httpx
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from openai import OpenAI

from .models import CreditTransaction, GeneratedImage, GeneratedPrompt, GenerationJob, ProductSnapshot, Shop


PROMPT_CATEGORIES = [
    "premium ecommerce hero",
    "bright clean studio",
    "aspirational lifestyle",
    "close-up material detail",
    "minimal editorial",
    "seasonal campaign",
    "social ad creative",
    "in-use product story",
    "gift or bundle scene",
    "luxury brand campaign",
]


class ShopifyClient:
    def __init__(self, shop: Shop):
        self.shop = shop
        self.endpoint = (
            f"https://{shop.shop_domain}/admin/api/"
            f"{settings.SHOPIFY_API_VERSION}/graphql.json"
        )

    def graphql(self, query, variables=None):
        response = httpx.post(
            self.endpoint,
            headers={"X-Shopify-Access-Token": self.shop.access_token},
            json={"query": query, "variables": variables or {}},
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(payload["errors"])
        return payload["data"]

    def sync_products(self):
        query = """
        query Products($after: String) {
          products(first: 50, after: $after) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id title descriptionHtml vendor productType status tags
              media(first: 20) {
                nodes {
                  ... on MediaImage { id image { url altText width height } }
                }
              }
              variants(first: 50) { nodes { id title sku price } }
            }
          }
        }
        """
        after = None
        while True:
            data = self.graphql(query, {"after": after})["products"]
            for product in data["nodes"]:
                ProductSnapshot.objects.update_or_create(
                    shop=self.shop,
                    shopify_product_id=product["id"],
                    defaults={
                        "title": product["title"],
                        "description": product["descriptionHtml"],
                        "vendor": product["vendor"],
                        "product_type": product["productType"],
                        "status": product["status"],
                        "tags": product["tags"],
                        "images": [
                            {"id": node["id"], **node["image"]}
                            for node in product["media"]["nodes"]
                            if node.get("image")
                        ],
                        "variants": product["variants"]["nodes"],
                    },
                )
            if not data["pageInfo"]["hasNextPage"]:
                break
            after = data["pageInfo"]["endCursor"]

    def attach_images(self, job, images):
        mutation = """
        mutation AddProductMedia($product: ProductUpdateInput!, $media: [CreateMediaInput!]) {
          productUpdate(product: $product, media: $media) {
            product { id }
            userErrors { field message }
          }
        }
        """
        media = [
            {
                "originalSource": image.resolved_url,
                "mediaContentType": "IMAGE",
                "alt": f"{job.product.title} — AI generated product image",
            }
            for image in images
        ]
        result = self.graphql(
            mutation,
            {"product": {"id": job.product.shopify_product_id}, "media": media},
        )["productUpdate"]
        if result["userErrors"]:
            raise RuntimeError(result["userErrors"])
        now = timezone.now()
        for image in images:
            image.added_to_shopify_at = now
            image.save(update_fields=["added_to_shopify_at"])


def build_oauth_url(shop_domain):
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.SHOPIFY_API_KEY,
        "scope": settings.SHOPIFY_SCOPES,
        "redirect_uri": settings.SHOPIFY_REDIRECT_URI,
        "state": state,
    }
    return f"https://{shop_domain}/admin/oauth/authorize?{urlencode(params)}", state


def verify_shopify_hmac(params):
    supplied = params.get("hmac", "")
    message = "&".join(
        f"{key}={value}" for key, value in sorted(params.items()) if key not in {"hmac", "signature"}
    )
    digest = hmac.new(
        settings.SHOPIFY_API_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(digest, supplied)


def verify_webhook_hmac(raw_body, supplied):
    digest = base64.b64encode(
        hmac.new(settings.SHOPIFY_API_SECRET.encode(), raw_body, hashlib.sha256).digest()
    ).decode()
    return bool(supplied) and hmac.compare_digest(digest, supplied)


def exchange_oauth_code(shop_domain, code):
    response = httpx.post(
        f"https://{shop_domain}/admin/oauth/access_token",
        json={
            "client_id": settings.SHOPIFY_API_KEY,
            "client_secret": settings.SHOPIFY_API_SECRET,
            "code": code,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def generate_prompt_ideas(product):
    if not settings.OPENAI_API_KEY:
        return [
            (
                f"{category.title()} photograph of {product.title}. Preserve the exact product "
                f"shape, color, materials, branding, and proportions. {product.description[:280]} "
                "Commercial product photography, realistic lighting, no extra text, no altered logo."
            )
            for category in PROMPT_CATEGORIES
        ]

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.responses.create(
        model=settings.OPENAI_TEXT_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    "You are an ecommerce art director. Return JSON with a prompts array containing "
                    "exactly 10 distinct, production-ready image prompts. Preserve product identity. "
                    "Cover studio, lifestyle, detail, seasonal, social, bundle, and premium concepts."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "title": product.title,
                    "description": product.description,
                    "vendor": product.vendor,
                    "product_type": product.product_type,
                    "tags": product.tags,
                    "variants": product.variants,
                }),
            },
        ],
        text={"format": {"type": "json_schema", "name": "prompt_list", "schema": {
            "type": "object",
            "properties": {"prompts": {"type": "array", "items": {"type": "string"}, "minItems": 10, "maxItems": 10}},
            "required": ["prompts"],
            "additionalProperties": False,
        }}},
    )
    return json.loads(response.output_text)["prompts"]


@transaction.atomic
def reserve_credits(job, amount):
    shop = Shop.objects.select_for_update().get(pk=job.shop_id)
    if shop.credits_balance < amount:
        raise ValueError("Not enough credits")
    shop.credits_balance -= amount
    shop.save(update_fields=["credits_balance"])
    job.credits_used += amount
    job.save(update_fields=["credits_used"])
    CreditTransaction.objects.create(
        shop=shop, kind=CreditTransaction.Kind.DEBIT, amount=amount,
        reason="AI image generation", job=job,
    )


@transaction.atomic
def refund_credit(job, amount=1):
    shop = Shop.objects.select_for_update().get(pk=job.shop_id)
    shop.credits_balance += amount
    shop.save(update_fields=["credits_balance"])
    job.credits_used = max(0, job.credits_used - amount)
    job.save(update_fields=["credits_used"])
    CreditTransaction.objects.create(
        shop=shop, kind=CreditTransaction.Kind.REFUND, amount=amount,
        reason="Generation failed", job=job,
    )


def generate_image(image):
    image.status = GeneratedImage.Status.PROCESSING
    image.save(update_fields=["status"])
    if not settings.OPENAI_API_KEY:
        image.image_url = f"https://picsum.photos/seed/{image.pk}/1024/1024"
        image.status = GeneratedImage.Status.COMPLETED
        image.save(update_fields=["image_url", "status"])
        return

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    result = client.images.generate(
        model=settings.OPENAI_IMAGE_MODEL,
        prompt=image.prompt.prompt,
        size="1024x1024",
        quality="medium",
        output_format="webp",
    )
    image_bytes = base64.b64decode(result.data[0].b64_json)
    image.image.save(f"image-{image.pk}.webp", ContentFile(image_bytes), save=False)
    image.status = GeneratedImage.Status.COMPLETED
    image.save(update_fields=["image", "status"])
