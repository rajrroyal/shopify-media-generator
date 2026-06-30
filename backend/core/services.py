import base64
import hashlib
import hmac
import json
import re
import secrets
from io import BytesIO
from urllib.parse import urlencode
from urllib.parse import urljoin

import httpx
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from openai import OpenAI
from rest_framework.exceptions import APIException

from .models import (
    CreditPurchase,
    CreditTransaction,
    GeneratedImage,
    GeneratedPrompt,
    GenerationJob,
    Shop,
)


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


class ShopifyReauthorizationRequired(APIException):
    status_code = 401
    default_detail = "Shopify access expired. Reconnecting your store…"
    default_code = "shopify_reauthorization_required"


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
        if response.status_code == 401:
            Shop.objects.filter(pk=self.shop.pk).update(access_token="")
            self.shop.access_token = ""
            raise ShopifyReauthorizationRequired()
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(payload["errors"])
        return payload["data"]

    def fetch_shop_context(self):
        return self.graphql(
            """
            query CurrentShop {
              shop { name myshopifyDomain }
              currentAppInstallation {
                activeSubscriptions { id name status currentPeriodEnd }
              }
            }
            """
        )

    @staticmethod
    def _product_payload(product):
        return {
            "id": product["id"].rsplit("/", 1)[-1],
            "shopify_product_id": product["id"],
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
        }

    def fetch_products(self, search=""):
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
        products = []
        while True:
            data = self.graphql(query, {"after": after})["products"]
            for product in data["nodes"]:
                payload = self._product_payload(product)
                if not search or search.lower() in payload["title"].lower():
                    products.append(payload)
            if not data["pageInfo"]["hasNextPage"]:
                break
            after = data["pageInfo"]["endCursor"]
        return products

    def fetch_product(self, product_id):
        raw_id = str(product_id)
        if raw_id.startswith("gid://shopify/Product/"):
            raw_id = raw_id.rsplit("/", 1)[-1]
        if not re.fullmatch(r"\d+", raw_id):
            raise ValueError("Invalid Shopify product ID.")
        query = """
        query Product($id: ID!) {
          product(id: $id) {
            id title descriptionHtml vendor productType status tags
            media(first: 20) {
              nodes {
                ... on MediaImage { id image { url altText width height } }
              }
            }
            variants(first: 50) { nodes { id title sku price } }
          }
        }
        """
        product = self.graphql(
            query, {"id": f"gid://shopify/Product/{raw_id}"}
        )["product"]
        if not product:
            raise ValueError("Shopify product not found.")
        return self._product_payload(product)

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
                "originalSource": self._public_image_url(image),
                "mediaContentType": "IMAGE",
                "alt": f"{job.product_data.get('title', 'Product')} — AI generated product image",
            }
            for image in images
        ]
        result = self.graphql(
            mutation,
            {"product": {"id": job.shopify_product_id}, "media": media},
        )["productUpdate"]
        if result["userErrors"]:
            raise RuntimeError(result["userErrors"])
        now = timezone.now()
        for image in images:
            image.added_to_shopify_at = now
            image.save(update_fields=["added_to_shopify_at"])

    @staticmethod
    def _public_image_url(image):
        url = image.resolved_url
        if url.startswith(("https://", "http://")):
            return url
        if not settings.BACKEND_URL:
            raise RuntimeError("BACKEND_URL is required to publish locally stored images.")
        return urljoin(f"{settings.BACKEND_URL}/", url.lstrip("/"))


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
    title = product.get("title", "product")
    description = product.get("description", "")
    if not settings.OPENAI_API_KEY:
        return [
            (
                f"{category.title()} photograph of {title}. Preserve the exact product "
                f"shape, color, materials, branding, and proportions. {description[:280]} "
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
                    "title": title,
                    "description": description,
                    "vendor": product.get("vendor", ""),
                    "product_type": product.get("product_type", ""),
                    "tags": product.get("tags", []),
                    "variants": product.get("variants", []),
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
    plan_amount = min(shop.plan_credits_balance, amount)
    purchased_amount = amount - plan_amount
    shop.plan_credits_balance -= plan_amount
    shop.purchased_credits_balance -= purchased_amount
    shop.save(update_fields=["plan_credits_balance", "purchased_credits_balance"])
    job.credits_used += amount
    job.save(update_fields=["credits_used"])
    CreditTransaction.objects.create(
        shop=shop, kind=CreditTransaction.Kind.DEBIT, amount=amount,
        plan_amount=plan_amount, purchased_amount=purchased_amount,
        reason="AI image generation", job=job,
    )


@transaction.atomic
def refund_credit(job, amount=1):
    shop = Shop.objects.select_for_update().get(pk=job.shop_id)
    allocations = CreditTransaction.objects.filter(shop=shop, job=job).aggregate(
        debited_plan=Sum("plan_amount", filter=Q(kind=CreditTransaction.Kind.DEBIT)),
        debited_purchased=Sum(
            "purchased_amount", filter=Q(kind=CreditTransaction.Kind.DEBIT)
        ),
        refunded_plan=Sum("plan_amount", filter=Q(kind=CreditTransaction.Kind.REFUND)),
        refunded_purchased=Sum(
            "purchased_amount", filter=Q(kind=CreditTransaction.Kind.REFUND)
        ),
    )
    outstanding_plan = (allocations["debited_plan"] or 0) - (allocations["refunded_plan"] or 0)
    plan_amount = min(amount, outstanding_plan)
    purchased_amount = amount - plan_amount
    shop.plan_credits_balance += plan_amount
    shop.purchased_credits_balance += purchased_amount
    shop.save(update_fields=["plan_credits_balance", "purchased_credits_balance"])
    job.credits_used = max(0, job.credits_used - amount)
    job.save(update_fields=["credits_used"])
    CreditTransaction.objects.create(
        shop=shop, kind=CreditTransaction.Kind.REFUND, amount=amount,
        plan_amount=plan_amount, purchased_amount=purchased_amount,
        reason="Generation failed", job=job,
    )


@transaction.atomic
def update_credit_purchase(purchase, status):
    """Apply a Shopify purchase update exactly once."""
    purchase = CreditPurchase.objects.select_for_update().get(pk=purchase.pk)
    purchase.status = status if status in CreditPurchase.Status.values else CreditPurchase.Status.ERROR
    update_fields = ["status", "updated_at"]

    if purchase.status == CreditPurchase.Status.ACTIVE and not purchase.credited_at:
        shop = Shop.objects.select_for_update().get(pk=purchase.shop_id)
        shop.purchased_credits_balance += purchase.credits
        shop.save(update_fields=["purchased_credits_balance"])
        CreditTransaction.objects.create(
            shop=shop,
            kind=CreditTransaction.Kind.CREDIT,
            amount=purchase.credits,
            purchased_amount=purchase.credits,
            reason=f"Purchased {purchase.pack_name}",
            credit_purchase=purchase,
        )
        purchase.credited_at = timezone.now()
        update_fields.append("credited_at")

    purchase.save(update_fields=update_fields)
    return purchase


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
