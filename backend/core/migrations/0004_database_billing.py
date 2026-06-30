import datetime
import uuid

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def seed_billing(apps, schema_editor):
    SubscriptionPlan = apps.get_model("core", "SubscriptionPlan")
    CreditPack = apps.get_model("core", "CreditPack")
    Shop = apps.get_model("core", "Shop")

    plan_values = [
        {
            "slug": "free",
            "name": "Free",
            "price": 0,
            "monthly_credits": 10,
            "description": "Try PixelMint on a few products.",
            "sort_order": 0,
        },
        {
            "slug": "starter",
            "name": "Starter",
            "price": 9,
            "monthly_credits": 60,
            "description": "For new and growing storefronts.",
            "sort_order": 10,
        },
        {
            "slug": "pro",
            "name": "Pro",
            "price": 29,
            "monthly_credits": 200,
            "description": "For active brands publishing weekly.",
            "featured": True,
            "sort_order": 20,
        },
        {
            "slug": "growth",
            "name": "Growth",
            "price": 79,
            "monthly_credits": 550,
            "description": "For teams and larger catalogs.",
            "sort_order": 30,
        },
    ]
    plans = {}
    for values in plan_values:
        plan, _ = SubscriptionPlan.objects.get_or_create(
            slug=values["slug"], defaults=values
        )
        plans[plan.slug] = plan

    pack_values = [
        {
            "slug": "boost-50",
            "name": "Quick boost",
            "price": 9,
            "credits": 50,
            "description": "A small one-time top-up.",
            "sort_order": 10,
        },
        {
            "slug": "boost-150",
            "name": "Campaign pack",
            "price": 25,
            "credits": 150,
            "description": "Extra room for a campaign.",
            "sort_order": 20,
        },
        {
            "slug": "boost-500",
            "name": "Catalog pack",
            "price": 75,
            "credits": 500,
            "description": "A larger catalog top-up.",
            "sort_order": 30,
        },
    ]
    for values in pack_values:
        CreditPack.objects.get_or_create(slug=values["slug"], defaults=values)

    reset_at = timezone.now() + datetime.timedelta(days=30)
    for shop in Shop.objects.all().iterator():
        shop.plan = plans.get(shop.legacy_plan, plans["free"])
        shop.next_plan_credit_reset_at = reset_at
        shop.save(update_fields=["plan", "next_plan_credit_reset_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_sync_shop_permission_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="CreditPack",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("slug", models.SlugField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=100)),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=8,
                        validators=[django.core.validators.MinValueValidator(0.01)],
                    ),
                ),
                (
                    "credits",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MinValueValidator(1)]
                    ),
                ),
                ("description", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["sort_order", "price", "id"]},
        ),
        migrations.CreateModel(
            name="SubscriptionPlan",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("slug", models.SlugField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=100)),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=8,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                ("monthly_credits", models.PositiveIntegerField()),
                ("description", models.CharField(blank=True, max_length=255)),
                ("featured", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["sort_order", "price", "id"]},
        ),
        migrations.RenameField(
            model_name="shop",
            old_name="plan",
            new_name="legacy_plan",
        ),
        migrations.RenameField(
            model_name="shop",
            old_name="credits_balance",
            new_name="plan_credits_balance",
        ),
        migrations.AlterField(
            model_name="shop",
            name="plan_credits_balance",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="shop",
            name="next_plan_credit_reset_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="shop",
            name="purchased_credits_balance",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="shop",
            name="shopify_subscription_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="shop",
            name="plan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="shops",
                to="core.subscriptionplan",
            ),
        ),
        migrations.AddField(
            model_name="credittransaction",
            name="plan_amount",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="credittransaction",
            name="purchased_amount",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="CreditPurchase",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "reference",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("pack_name", models.CharField(max_length=100)),
                ("credits", models.PositiveIntegerField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=8)),
                ("currency", models.CharField(default="USD", max_length=3)),
                (
                    "shopify_purchase_id",
                    models.CharField(
                        blank=True, max_length=255, null=True, unique=True
                    ),
                ),
                ("shopify_name", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("ACTIVE", "Active"),
                            ("DECLINED", "Declined"),
                            ("EXPIRED", "Expired"),
                            ("ERROR", "Error"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("credited_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "pack",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="purchases",
                        to="core.creditpack",
                    ),
                ),
                (
                    "shop",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="credit_purchases",
                        to="core.shop",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddField(
            model_name="credittransaction",
            name="credit_purchase",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="credit_transaction",
                to="core.creditpurchase",
            ),
        ),
        migrations.RunPython(seed_billing, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="shop",
            name="legacy_plan",
        ),
    ]
