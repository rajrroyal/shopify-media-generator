import core.models
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="Shop",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False)),
                ("shop_domain", models.CharField(max_length=255, unique=True)),
                ("access_token", models.TextField(blank=True)),
                ("scope", models.TextField(blank=True)),
                ("plan", models.CharField(choices=[("free", "Free"), ("starter", "Starter"), ("pro", "Pro"), ("growth", "Growth")], default="free", max_length=20)),
                ("credits_balance", models.PositiveIntegerField(default=10)),
                ("is_active", models.BooleanField(default=True)),
                ("is_staff", models.BooleanField(default=False)),
                ("installed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("groups", models.ManyToManyField(blank=True, related_name="user_set", related_query_name="user", to="auth.group")),
                ("user_permissions", models.ManyToManyField(blank=True, related_name="user_set", related_query_name="user", to="auth.permission")),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="ProductSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shopify_product_id", models.CharField(max_length=100)),
                ("title", models.CharField(max_length=500)),
                ("description", models.TextField(blank=True)),
                ("vendor", models.CharField(blank=True, max_length=255)),
                ("product_type", models.CharField(blank=True, max_length=255)),
                ("status", models.CharField(default="ACTIVE", max_length=50)),
                ("tags", models.JSONField(default=list)),
                ("images", models.JSONField(default=list)),
                ("variants", models.JSONField(default=list)),
                ("synced_at", models.DateTimeField(auto_now=True)),
                ("shop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="products", to="core.shop")),
            ],
            options={"ordering": ["title"]},
        ),
        migrations.CreateModel(
            name="GenerationJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("prompts_ready", "Prompts ready"), ("queued", "Queued"), ("processing", "Processing"), ("completed", "Completed"), ("partial", "Partially completed"), ("failed", "Failed")], default="draft", max_length=30)),
                ("source_images", models.JSONField(default=list)),
                ("credits_used", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="generation_jobs", to="core.productsnapshot")),
                ("shop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="generation_jobs", to="core.shop")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="GeneratedPrompt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("prompt", models.TextField()),
                ("is_selected", models.BooleanField(default=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="prompts", to="core.generationjob")),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.CreateModel(
            name="GeneratedImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(blank=True, upload_to=core.models.generated_image_path)),
                ("image_url", models.URLField(blank=True, max_length=2000)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("completed", "Completed"), ("failed", "Failed")], default="pending", max_length=20)),
                ("shopify_media_id", models.CharField(blank=True, max_length=255)),
                ("is_selected", models.BooleanField(default=True)),
                ("error_message", models.TextField(blank=True)),
                ("added_to_shopify_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="core.generationjob")),
                ("prompt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="core.generatedprompt")),
            ],
        ),
        migrations.CreateModel(
            name="CreditTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("credit", "Credit"), ("debit", "Debit"), ("refund", "Refund")], max_length=10)),
                ("amount", models.PositiveIntegerField()),
                ("reason", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("job", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.generationjob")),
                ("shop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="credit_transactions", to="core.shop")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="productsnapshot",
            constraint=models.UniqueConstraint(fields=("shop", "shopify_product_id"), name="unique_shop_product"),
        ),
    ]
