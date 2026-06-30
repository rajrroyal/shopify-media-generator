from rest_framework import serializers

from .models import CreditPack, GeneratedImage, GeneratedPrompt, GenerationJob, Shop, SubscriptionPlan


class ShopSerializer(serializers.ModelSerializer):
    plan = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    credits_balance = serializers.IntegerField(read_only=True)

    class Meta:
        model = Shop
        fields = [
            "shop_domain",
            "plan",
            "credits_balance",
            "plan_credits_balance",
            "purchased_credits_balance",
            "next_plan_credit_reset_at",
            "installed_at",
        ]


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="slug", read_only=True)
    credits = serializers.IntegerField(source="monthly_credits", read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = ["id", "slug", "name", "price", "credits", "description", "featured"]


class CreditPackSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="slug", read_only=True)

    class Meta:
        model = CreditPack
        fields = ["id", "slug", "name", "price", "credits", "description"]


class PromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedPrompt
        fields = ["id", "prompt", "is_selected", "sort_order"]


class ImageSerializer(serializers.ModelSerializer):
    url = serializers.CharField(source="resolved_url", read_only=True)

    class Meta:
        model = GeneratedImage
        fields = [
            "id", "prompt_id", "url", "status", "is_selected", "shopify_media_id",
            "error_message", "added_to_shopify_at", "created_at",
        ]


class JobSerializer(serializers.ModelSerializer):
    product = serializers.JSONField(source="product_data", read_only=True)
    prompts = PromptSerializer(many=True, read_only=True)
    images = ImageSerializer(many=True, read_only=True)

    class Meta:
        model = GenerationJob
        fields = [
            "id", "product", "status", "source_images", "credits_used",
            "error_message", "prompts", "images", "created_at", "updated_at",
        ]


class CreateJobSerializer(serializers.Serializer):
    product_id = serializers.CharField(max_length=100)
    source_images = serializers.ListField(child=serializers.URLField(), required=False, default=list)


class PromptInputSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    prompt = serializers.CharField(max_length=4000)
    is_selected = serializers.BooleanField(default=True)


class GenerateImagesSerializer(serializers.Serializer):
    prompts = PromptInputSerializer(many=True)


class ImageSelectionSerializer(serializers.Serializer):
    image_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
