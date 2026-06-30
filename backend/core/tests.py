from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import (
    CreditPack,
    CreditPurchase,
    CreditTransaction,
    GenerationJob,
    Shop,
    SubscriptionPlan,
)
from .services import refund_credit, reserve_credits, update_credit_purchase


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
