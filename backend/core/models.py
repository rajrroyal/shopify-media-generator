import uuid

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class SubscriptionPlan(models.Model):
    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    price = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(0)]
    )
    monthly_credits = models.PositiveIntegerField()
    description = models.CharField(max_length=255, blank=True)
    featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "price", "id"]

    def __str__(self):
        return f"{self.name} (${self.price}/month)"


class CreditPack(models.Model):
    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    price = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(0.01)]
    )
    credits = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "price", "id"]

    def __str__(self):
        return f"{self.name} ({self.credits} credits)"


class AppSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_value(cls, key, default=""):
        return cls.objects.filter(key=key).values_list("value", flat=True).first() or default

    def __str__(self):
        return self.key


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
    shop_domain = models.CharField(max_length=255, unique=True)
    access_token = models.TextField(blank=True)
    access_token_expires_at = models.DateTimeField(null=True, blank=True)
    refresh_token = models.TextField(blank=True)
    refresh_token_expires_at = models.DateTimeField(null=True, blank=True)
    scope = models.TextField(blank=True)
    plan = models.ForeignKey(
        SubscriptionPlan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shops",
    )
    plan_credits_balance = models.PositiveIntegerField(default=0)
    purchased_credits_balance = models.PositiveIntegerField(default=0)
    shopify_subscription_id = models.CharField(max_length=255, blank=True)
    next_plan_credit_reset_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    installed_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ShopManager()
    USERNAME_FIELD = "shop_domain"

    def __str__(self):
        return self.shop_domain

    @property
    def credits_balance(self):
        return self.plan_credits_balance + self.purchased_credits_balance


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
    shopify_product_id = models.CharField(max_length=100)
    product_data = models.JSONField(default=dict)
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
    title = models.CharField(max_length=80, blank=True)
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
    plan_amount = models.PositiveIntegerField(default=0)
    purchased_amount = models.PositiveIntegerField(default=0)
    reason = models.CharField(max_length=255)
    job = models.ForeignKey(GenerationJob, null=True, blank=True, on_delete=models.SET_NULL)
    credit_purchase = models.OneToOneField(
        "CreditPurchase",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="credit_transaction",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class CreditPurchase(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACTIVE = "ACTIVE", "Active"
        DECLINED = "DECLINED", "Declined"
        EXPIRED = "EXPIRED", "Expired"
        ERROR = "ERROR", "Error"

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="credit_purchases")
    pack = models.ForeignKey(
        CreditPack,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchases",
    )
    pack_name = models.CharField(max_length=100)
    credits = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    shopify_purchase_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    shopify_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    credited_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.shop} — {self.pack_name} — {self.status}"
