"""Backward-compatible service exports.

New code should import from the focused service module directly.
"""

from .credits import refund_credit, reserve_credits, update_credit_purchase
from .images import generate_image
from .prompts import generate_prompt_ideas
from .shopify import (
    ShopifyClient,
    ShopifyReauthorizationRequired,
    build_oauth_url,
    ensure_shopify_access_token,
    exchange_oauth_code,
    exchange_session_token,
    refresh_shopify_token,
    store_shopify_tokens,
    verify_shopify_hmac,
    verify_webhook_hmac,
)

__all__ = [
    "ShopifyClient",
    "ShopifyReauthorizationRequired",
    "build_oauth_url",
    "ensure_shopify_access_token",
    "exchange_oauth_code",
    "exchange_session_token",
    "generate_image",
    "generate_prompt_ideas",
    "refund_credit",
    "refresh_shopify_token",
    "reserve_credits",
    "store_shopify_tokens",
    "update_credit_purchase",
    "verify_shopify_hmac",
    "verify_webhook_hmac",
]
