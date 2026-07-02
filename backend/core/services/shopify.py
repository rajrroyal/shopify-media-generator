"""Shopify Admin API, OAuth, webhook, and token services."""

import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode
from urllib.parse import urljoin

import httpx
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import APIException

from ..models import Shop


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
        if not settings.FRONTEND_URL:
            raise RuntimeError("FRONTEND_URL is required to publish locally stored images.")
        return urljoin(f"{settings.FRONTEND_URL}/", url.lstrip("/"))


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
        data={
            "client_id": settings.SHOPIFY_API_KEY,
            "client_secret": settings.SHOPIFY_API_SECRET,
            "code": code,
            "expiring": "1",
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def exchange_session_token(shop_domain, session_token):
    response = httpx.post(
        f"https://{shop_domain}/admin/oauth/access_token",
        data={
            "client_id": settings.SHOPIFY_API_KEY,
            "client_secret": settings.SHOPIFY_API_SECRET,
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": session_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
            "requested_token_type": (
                "urn:shopify:params:oauth:token-type:offline-access-token"
            ),
            "expiring": "1",
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def refresh_shopify_token(shop_domain, refresh_token):
    response = httpx.post(
        f"https://{shop_domain}/admin/oauth/access_token",
        data={
            "client_id": settings.SHOPIFY_API_KEY,
            "client_secret": settings.SHOPIFY_API_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def store_shopify_tokens(shop, payload):
    now = timezone.now()
    shop.access_token = payload["access_token"]
    shop.scope = payload.get("scope", shop.scope)
    shop.access_token_expires_at = (
        now + timedelta(seconds=int(payload["expires_in"]))
        if payload.get("expires_in")
        else None
    )
    if payload.get("refresh_token"):
        shop.refresh_token = payload["refresh_token"]
        shop.refresh_token_expires_at = (
            now + timedelta(seconds=int(payload["refresh_token_expires_in"]))
            if payload.get("refresh_token_expires_in")
            else None
        )
    shop.save(update_fields=[
        "access_token",
        "access_token_expires_at",
        "refresh_token",
        "refresh_token_expires_at",
        "scope",
        "updated_at",
    ])


def ensure_shopify_access_token(shop, session_token):
    refresh_before = timezone.now() + timedelta(minutes=5)
    if shop.access_token and (
        shop.access_token_expires_at is None
        or shop.access_token_expires_at > refresh_before
    ):
        return

    payload = None
    if shop.refresh_token and (
        shop.refresh_token_expires_at is None
        or shop.refresh_token_expires_at > refresh_before
    ):
        try:
            payload = refresh_shopify_token(shop.shop_domain, shop.refresh_token)
        except httpx.HTTPStatusError:
            payload = None
    if payload is None:
        payload = exchange_session_token(shop.shop_domain, session_token)
    store_shopify_tokens(shop, payload)
