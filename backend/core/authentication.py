import jwt
from django.conf import settings
from rest_framework import authentication, exceptions

from .models import Shop


class ShopifySessionAuthentication(authentication.BaseAuthentication):
    """Validate Shopify App Bridge session tokens.

    During local development only, X-Shop-Domain can select a seeded shop.
    """

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode()
        if auth_header.startswith("Bearer ") and settings.SHOPIFY_API_SECRET:
            token = auth_header.removeprefix("Bearer ").strip()
            try:
                payload = jwt.decode(
                    token,
                    settings.SHOPIFY_API_SECRET,
                    algorithms=["HS256"],
                    audience=settings.SHOPIFY_API_KEY,
                    options={"require": ["exp", "dest"]},
                )
                domain = payload["dest"].removeprefix("https://").rstrip("/")
                shop = Shop.objects.get(shop_domain=domain, is_active=True)
                return shop, payload
            except (jwt.PyJWTError, Shop.DoesNotExist) as exc:
                raise exceptions.AuthenticationFailed("Invalid Shopify session token") from exc

        if settings.DEBUG:
            domain = (
                request.headers.get("X-Shop-Domain")
                or request.query_params.get("shop")
                or "demo-store.myshopify.com"
            )
            shop = Shop.objects.filter(shop_domain=domain, is_active=True).first()
            if shop:
                return shop, None

        return None
