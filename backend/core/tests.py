import json
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import httpx
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .models import (
    AppSetting,
    CreditPack,
    CreditPurchase,
    CreditTransaction,
    GeneratedVideo,
    GenerationJob,
    Shop,
    SubscriptionPlan,
)
from .services.credits import refund_credit, reserve_credits, update_credit_purchase
from .services.images import _cap_dimensions
from .services.prompts import generate_prompt_ideas
from .services.videos import _vertical_reference, generate_video_prompt, submit_video
from .services.shopify import ensure_shopify_access_token


class ImageDimensionTests(TestCase):
    def test_custom_dimensions_are_aligned_to_multiples_of_16(self):
        width, height = _cap_dimensions(1080, 1350, 2048)

        self.assertEqual((width, height), (1088, 1344))
        self.assertEqual(width % 16, 0)
        self.assertEqual(height % 16, 0)

    def test_scaled_dimensions_remain_within_maximum(self):
        width, height = _cap_dimensions(4000, 3000, 2048)

        self.assertLessEqual(max(width, height), 2048)
        self.assertEqual((width % 16, height % 16), (0, 0))


class VideoReferenceTests(TestCase):
    def test_reference_is_centered_on_padded_vertical_canvas(self):
        source = BytesIO()
        product = Image.new("RGB", (1600, 900), "white")
        product.paste("red", (600, 200, 1000, 700))
        product.save(source, format="JPEG")

        framed = Image.open(BytesIO(_vertical_reference(source.getvalue())))

        self.assertEqual(framed.size, (720, 1280))
        self.assertNotEqual(framed.getpixel((0, 0)), framed.getpixel((360, 640)))


@override_settings(OPENAI_API_KEY="")
class PromptGenerationTests(TestCase):
    def setUp(self):
        AppSetting.objects.update_or_create(
            key="ai_images_prompt",
            defaults={"value": (
                "Product: {product_title}\n"
                "Dimensions: {product_dimensions}\n"
                "Description: {product_description}"
            )},
        )
        self.product = {
            "title": "Test bottle",
            "description": "A blue glass bottle",
            "vendor": "Example Brand",
            "product_type": "Glassware",
            "images": [
                {"url": "https://cdn.example.com/one.jpg", "width": 800, "height": 1200},
                {"url": "https://cdn.example.com/two.jpg", "width": 1600, "height": 900},
            ],
        }

    def test_primary_selected_image_controls_dimensions(self):
        prompts = generate_prompt_ideas(
            self.product,
            ["https://cdn.example.com/two.jpg"],
        )

        self.assertEqual(len(prompts), 7)
        self.assertEqual(prompts[0]["title"], "Podium / Platform")
        self.assertIn("1600 × 900 pixels", prompts[0]["description"])

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("core.services.prompts.OpenAI")
    @patch("core.services.prompts.httpx.get")
    def test_openai_receives_primary_image_and_structured_schema(self, http_get, openai):
        http_get.return_value.content = b"image-bytes"
        http_get.return_value.headers = {"content-type": "image/jpeg"}
        http_get.return_value.raise_for_status.return_value = None
        openai.return_value.responses.create.return_value.output_text = json.dumps({
            "prompts": [
                {
                    "title": title,
                    "description": f"{title} scene for the blue bottle",
                }
                for title in [
                    "Podium",
                    "Splash",
                    "Lifestyle",
                    "Outdoor",
                    "Studio",
                    "Flat Lay",
                    "Reflection",
                ]
            ]
        })

        prompts = generate_prompt_ideas(
            self.product,
            ["https://cdn.example.com/one.jpg"],
        )

        self.assertEqual(len(prompts), 7)
        arguments = openai.return_value.responses.create.call_args.kwargs
        user_content = arguments["input"][1]["content"]
        self.assertIn("800 × 1200 pixels", user_content[0]["text"])
        self.assertEqual(user_content[1]["type"], "input_image")
        self.assertTrue(user_content[1]["image_url"].startswith("data:image/jpeg;base64,"))
        self.assertTrue(arguments["text"]["format"]["strict"])


@override_settings(CORS_ALLOWED_ORIGINS=["https://frontend.example.com"])
class CorsTests(TestCase):
    def test_shop_domain_header_is_allowed_in_preflight(self):
        response = self.client.options(
            "/api/me/",
            HTTP_ORIGIN="https://frontend.example.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,x-shop-domain",
        )

        self.assertEqual(response.status_code, 200)
        allowed_headers = {
            header.strip().lower()
            for header in response["Access-Control-Allow-Headers"].split(",")
        }
        self.assertIn("x-shop-domain", allowed_headers)


class ShopifyTokenExchangeTests(TestCase):
    @patch("core.services.shopify.exchange_session_token")
    def test_session_token_is_exchanged_and_stored(self, exchange):
        exchange.return_value = {
            "access_token": "offline-access-token",
            "expires_in": 3600,
            "refresh_token": "offline-refresh-token",
            "refresh_token_expires_in": 7776000,
            "scope": "read_products,write_products",
        }
        shop = Shop.objects.create_user("exchange.myshopify.com")

        ensure_shopify_access_token(shop, "app-bridge-session-token")

        shop.refresh_from_db()
        self.assertEqual(shop.access_token, "offline-access-token")
        self.assertEqual(shop.refresh_token, "offline-refresh-token")
        self.assertIsNotNone(shop.access_token_expires_at)
        self.assertIsNotNone(shop.refresh_token_expires_at)
        exchange.assert_called_once_with(
            "exchange.myshopify.com",
            "app-bridge-session-token",
        )


class CreditAccountingTests(TestCase):
    def setUp(self):
        self.plan = SubscriptionPlan.objects.create(
            slug="test",
            name="Test",
            price=Decimal("10.00"),
            monthly_credits=10,
        )
        self.shop = Shop.objects.create_user(
            "credits.myshopify.com",
            plan=self.plan,
            plan_credits_balance=2,
            purchased_credits_balance=5,
        )
        self.job = GenerationJob.objects.create(
            shop=self.shop,
            shopify_product_id="1",
        )

    def test_plan_credits_are_spent_before_purchased_credits_and_refunded(self):
        reserve_credits(self.job, 4)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.plan_credits_balance, 0)
        self.assertEqual(self.shop.purchased_credits_balance, 3)

        debit = CreditTransaction.objects.get(kind=CreditTransaction.Kind.DEBIT)
        self.assertEqual((debit.plan_amount, debit.purchased_amount), (2, 2))

        refund_credit(self.job, 1)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.plan_credits_balance, 1)
        self.assertEqual(self.shop.purchased_credits_balance, 3)

    def test_approved_purchase_is_fulfilled_once(self):
        pack = CreditPack.objects.create(
            slug="test-pack",
            name="Test pack",
            price=Decimal("9.00"),
            credits=50,
        )
        purchase = CreditPurchase.objects.create(
            shop=self.shop,
            pack=pack,
            pack_name=pack.name,
            credits=pack.credits,
            amount=pack.price,
            shopify_name="Test purchase",
        )

        update_credit_purchase(purchase, CreditPurchase.Status.ACTIVE)
        update_credit_purchase(purchase, CreditPurchase.Status.ACTIVE)

        self.shop.refresh_from_db()
        purchase.refresh_from_db()
        self.assertEqual(self.shop.purchased_credits_balance, 55)
        self.assertIsNotNone(purchase.credited_at)
        self.assertEqual(
            CreditTransaction.objects.filter(credit_purchase=purchase).count(),
            1,
        )


@override_settings(OPENAI_API_KEY="")
class VideoGenerationTests(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create_user("video.myshopify.com")
        self.job = GenerationJob.objects.create(
            shop=self.shop,
            shopify_product_id="gid://shopify/Product/1",
            kind=GenerationJob.Kind.VIDEO,
            source_images=["https://cdn.example.com/product.jpg"],
        )
        self.video = GeneratedVideo.objects.create(
            job=self.job,
            prompt="Slow cinematic push-in",
            settings={"duration": "6"},
        )

    def test_video_prompt_has_safe_local_fallback(self):
        result = generate_video_prompt({"title": "Blue Bottle"}, self.job.source_images)
        self.assertIn("Blue Bottle", result["title"])
        self.assertIn("Preserve", result["prompt"])

    @override_settings(
        FAL_KEY="fal-test",
        VIDEO_MODELS={
            "preview": "fal-ai/test/wan",
            "quality": "fal-ai/test/video",
            "premium": "fal-ai/test/premium",
        },
    )
    @patch("core.services.videos._prepare_video_reference", return_value="https://app.example.com/reference.jpg")
    @patch("core.services.videos.httpx.post")
    def test_video_submission_persists_provider_request(self, post, prepare_reference):
        post.return_value.json.return_value = {"request_id": "request-123"}
        post.return_value.raise_for_status.return_value = None

        submit_video(self.video, "https://app.example.com/api/webhooks/fal/video/?token=test")

        self.video.refresh_from_db()
        self.assertEqual(self.video.provider_request_id, "request-123")
        self.assertEqual(self.video.status, GeneratedVideo.Status.QUEUED)
        self.assertEqual(self.video.model_id, "fal-ai/test/video")
        self.assertEqual(post.call_args.kwargs["json"]["image_url"], "https://app.example.com/reference.jpg")
        self.assertEqual(post.call_args.kwargs["json"]["duration"], "6")

    @override_settings(
        FAL_KEY="fal-test",
        VIDEO_MODELS={"preview": "fal-ai/wan/test", "quality": "fal-ai/wan/test"},
    )
    @patch("core.services.videos._prepare_video_reference", return_value="https://app.example.com/reference.jpg")
    @patch("core.services.videos.httpx.post")
    def test_wan_submission_omits_unsupported_duration(self, post, prepare_reference):
        post.return_value.json.return_value = {"request_id": "request-wan"}
        post.return_value.raise_for_status.return_value = None
        self.video.settings = {"duration": "10", "quality": "preview"}
        self.video.job.product_data = {
            "images": [{"url": self.job.source_images[0], "width": 1600, "height": 900}]
        }

        submit_video(self.video, "https://app.example.com/webhook")

        self.assertNotIn("duration", post.call_args.kwargs["json"])
        self.assertEqual(post.call_args.kwargs["json"]["aspect_ratio"], "9:16")
        self.assertEqual(self.video.model_id, "fal-ai/wan/test")

    @override_settings(
        FAL_KEY="fal-test",
        VIDEO_MODELS={"quality": "fal-ai/wan/test"},
    )
    @patch("core.services.videos._prepare_video_reference", return_value="https://app.example.com/reference.jpg")
    @patch("core.services.videos.httpx.post")
    def test_fal_validation_message_is_preserved(self, post, prepare_reference):
        request = httpx.Request("POST", "https://queue.fal.run/fal-ai/wan/test")
        response = httpx.Response(
            422,
            request=request,
            json={"detail": [{"loc": ["body", "image_url"], "msg": "URL is not reachable"}]},
        )
        post.return_value = response

        with self.assertRaisesRegex(RuntimeError, "image_url: URL is not reachable"):
            submit_video(self.video, "https://app.example.com/webhook")


@override_settings(
    SHOPIFY_BILLING_TEST_MODE=True,
    FRONTEND_URL="https://frontend.example.com",
)
class SubscriptionBillingTests(TestCase):
    def setUp(self):
        self.plan = SubscriptionPlan.objects.create(
            slug="billing-test",
            name="Billing test",
            price=Decimal("12.00"),
            monthly_credits=75,
        )
        self.shop = Shop.objects.create_user(
            "billing.myshopify.com",
            access_token="test-token",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.shop)

    @patch("core.views.ShopifyClient.graphql")
    def test_subscription_uses_test_mode_and_immediate_replacement(self, graphql):
        graphql.return_value = {
            "appSubscriptionCreate": {
                "appSubscription": {
                    "id": "gid://shopify/AppSubscription/1",
                    "status": "PENDING",
                    "test": True,
                },
                "confirmationUrl": "https://shopify.example.com/confirm",
                "userErrors": [],
            }
        }

        response = self.client.post(
            "/api/billing/subscribe/",
            {"plan_id": self.plan.slug},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["confirmation_url"],
            "https://shopify.example.com/confirm",
        )
        variables = graphql.call_args.args[1]
        self.assertIs(variables["test"], True)
        self.assertEqual(variables["replacementBehavior"], "APPLY_IMMEDIATELY")

    @patch("core.views.ShopifyClient.graphql")
    def test_shopify_user_error_is_returned_to_the_frontend(self, graphql):
        graphql.return_value = {
            "appSubscriptionCreate": {
                "appSubscription": None,
                "confirmationUrl": None,
                "userErrors": [
                    {"field": ["test"], "message": "Test shops require test charges."}
                ],
            }
        }

        response = self.client.post(
            "/api/billing/subscribe/",
            {"plan_id": self.plan.slug},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Test shops require test charges.")

    @patch("core.views.ShopifyClient.graphql")
    def test_missing_shopify_token_requires_reauthorization(self, graphql):
        self.shop.access_token = ""
        self.shop.save(update_fields=["access_token"])

        response = self.client.post(
            "/api/billing/subscribe/",
            {"plan_id": self.plan.slug},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.data["detail"].code,
            "shopify_reauthorization_required",
        )
        graphql.assert_not_called()


class CreditPurchaseBillingTests(TestCase):
    def setUp(self):
        self.pack = CreditPack.objects.create(
            slug="billing-pack",
            name="Billing pack",
            price=Decimal("9.00"),
            credits=50,
        )
        self.shop = Shop.objects.create_user(
            "purchase.myshopify.com",
            access_token="",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.shop)

    @patch("core.views.ShopifyClient.graphql")
    def test_missing_shopify_token_requires_reauthorization(self, graphql):
        response = self.client.post(
            "/api/billing/purchase-credits/",
            {"pack_id": self.pack.slug},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.data["detail"].code,
            "shopify_reauthorization_required",
        )
        graphql.assert_not_called()

    @patch("core.views.ShopifyClient.graphql")
    def test_purchase_name_does_not_expose_internal_reference(self, graphql):
        self.shop.access_token = "test-token"
        self.shop.save(update_fields=["access_token"])
        graphql.return_value = {
            "appPurchaseOneTimeCreate": {
                "appPurchaseOneTime": {
                    "id": "gid://shopify/AppPurchaseOneTime/1",
                    "status": "PENDING",
                },
                "confirmationUrl": "https://shopify.example.com/confirm",
                "userErrors": [],
            }
        }

        response = self.client.post(
            "/api/billing/purchase-credits/",
            {"pack_id": self.pack.slug},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        purchase = CreditPurchase.objects.get()
        self.assertEqual(purchase.shopify_name, "PixelMint 50 credit pack")
        self.assertNotIn(str(purchase.reference), purchase.shopify_name)
        self.assertEqual(
            graphql.call_args.args[1]["name"],
            "PixelMint 50 credit pack",
        )

    @patch("core.views.ShopifyClient.graphql")
    def test_return_from_shopify_reconciles_and_credits_purchase(self, graphql):
        self.shop.access_token = "test-token"
        self.shop.save(update_fields=["access_token"])
        purchase = CreditPurchase.objects.create(
            shop=self.shop,
            pack=self.pack,
            pack_name=self.pack.name,
            credits=self.pack.credits,
            amount=self.pack.price,
            shopify_name="PixelMint 50 credit pack",
            shopify_purchase_id="gid://shopify/AppPurchaseOneTime/1",
        )
        graphql.return_value = {
            "node": {
                "id": purchase.shopify_purchase_id,
                "status": "ACTIVE",
            }
        }

        response = self.client.post(
            "/api/billing/confirm-credit-purchase/",
            {"reference": str(purchase.reference)},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["credited"])
        self.assertEqual(response.data["purchased_credits_balance"], 50)
        purchase.refresh_from_db()
        self.assertIsNotNone(purchase.credited_at)
