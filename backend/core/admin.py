from django.contrib import admin

from .models import (
    AppSetting,
    CreditPack,
    CreditPurchase,
    CreditTransaction,
    GeneratedImage,
    GeneratedPrompt,
    GeneratedVideo,
    GenerationJob,
    Shop,
    SubscriptionPlan,
)


@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "updated_at")
    search_fields = ("key",)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "price",
        "monthly_credits",
        "featured",
        "is_active",
        "sort_order",
    )
    list_editable = ("price", "monthly_credits", "featured", "is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(CreditPack)
class CreditPackAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "price", "credits", "is_active", "sort_order")
    list_editable = ("price", "credits", "is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = (
        "shop_domain",
        "plan",
        "plan_credits_balance",
        "purchased_credits_balance",
        "total_credits",
        "is_active",
    )
    list_filter = ("plan", "is_active")
    search_fields = ("shop_domain",)
    autocomplete_fields = ("plan",)

    @admin.display(description="Total credits")
    def total_credits(self, obj):
        return obj.credits_balance


@admin.register(CreditPurchase)
class CreditPurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "shop",
        "pack_name",
        "credits",
        "amount",
        "status",
        "credited_at",
        "created_at",
    )
    list_filter = ("status", "pack")
    search_fields = ("shop__shop_domain", "shopify_purchase_id", "reference")
    readonly_fields = (
        "reference",
        "shopify_purchase_id",
        "shopify_name",
        "credited_at",
        "created_at",
        "updated_at",
    )


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "shop",
        "kind",
        "amount",
        "plan_amount",
        "purchased_amount",
        "reason",
        "created_at",
    )
    list_filter = ("kind",)
    search_fields = ("shop__shop_domain", "reason")
    readonly_fields = ("created_at",)


@admin.register(GenerationJob)
class GenerationJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "shop",
        "shopify_product_id",
        "status",
        "credits_used",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("id", "shop__shop_domain", "shopify_product_id")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("shop",)


@admin.register(GeneratedPrompt)
class GeneratedPromptAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "short_prompt", "is_selected", "sort_order")
    list_filter = ("is_selected",)
    search_fields = ("prompt", "job__id", "job__shop__shop_domain")
    autocomplete_fields = ("job",)

    @admin.display(description="Prompt")
    def short_prompt(self, obj):
        return obj.prompt[:100]


@admin.register(GeneratedImage)
class GeneratedImageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job",
        "status",
        "is_selected",
        "added_to_shopify_at",
        "created_at",
    )
    list_filter = ("status", "is_selected", "created_at")
    search_fields = ("job__id", "job__shop__shop_domain", "shopify_media_id")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("job", "prompt")


@admin.register(GeneratedVideo)
class GeneratedVideoAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "status", "model_id", "added_to_shopify_at", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("job__id", "provider_request_id", "shopify_media_id")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("job",)
