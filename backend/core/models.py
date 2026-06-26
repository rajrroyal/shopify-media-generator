import uuid

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone


class ShopManager(BaseUserManager):
    def create_user(self, shop_domain, password=None, **extra_fields):
        shop = self.model(shop_domain=shop_domain.lower(), **extra_fields)
        shop.set_password(password)
        shop.save(using=self._db)
        return shop

    def create_superuser(self, shop_domain, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(shop_domain, password, **extra_fields)


class Shop(AbstractBaseUser, PermissionsMixin):
    class Plan(models.TextChoices):
        FREE = "free", "Free"
        STARTER = "starter", "Starter"
        PRO = "pro", "Pro"
        GROWTH = "growth", "Growth"

    shop_domain = models.CharField(max_length=255, unique=True)
    access_token = models.TextField(blank=True)
    scope = models.TextField(blank=True)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)
    credits_balance = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    installed_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ShopManager()
    USERNAME_FIELD = "shop_domain"

    def __str__(self):
        return self.shop_domain


class ProductSnapshot(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="products")
    shopify_product_id = models.CharField(max_length=100)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    vendor = models.CharField(max_length=255, blank=True)
    product_type = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=50, default="ACTIVE")
    tags = models.JSONField(default=list)
    images = models.JSONField(default=list)
    variants = models.JSONField(default=list)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["shop", "shopify_product_id"], name="unique_shop_product")
        ]
        ordering = ["title"]


class GenerationJob(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PROMPTS_READY = "prompts_ready", "Prompts ready"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        PARTIAL = "partial", "Partially completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="generation_jobs")
    product = models.ForeignKey(ProductSnapshot, on_delete=models.PROTECT, related_name="generation_jobs")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    source_images = models.JSONField(default=list)
    credits_used = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class GeneratedPrompt(models.Model):
    job = models.ForeignKey(GenerationJob, on_delete=models.CASCADE, related_name="prompts")
    prompt = models.TextField()
    is_selected = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]


def generated_image_path(instance, filename):
    return f"generated/{instance.job.shop_id}/{instance.job_id}/{uuid.uuid4()}-{filename}"


class GeneratedImage(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    job = models.ForeignKey(GenerationJob, on_delete=models.CASCADE, related_name="images")
    prompt = models.ForeignKey(GeneratedPrompt, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=generated_image_path, blank=True)
    image_url = models.URLField(max_length=2000, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    shopify_media_id = models.CharField(max_length=255, blank=True)
    is_selected = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    added_to_shopify_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def resolved_url(self):
        if self.image:
            return self.image.url
        return self.image_url


class CreditTransaction(models.Model):
    class Kind(models.TextChoices):
        CREDIT = "credit", "Credit"
        DEBIT = "debit", "Debit"
        REFUND = "refund", "Refund"

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="credit_transactions")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    job = models.ForeignKey(GenerationJob, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
