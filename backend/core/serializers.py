from rest_framework import serializers

from .models import GeneratedImage, GeneratedPrompt, GenerationJob, ProductSnapshot, Shop


class ShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = ["shop_domain", "plan", "credits_balance", "installed_at"]


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSnapshot
        fields = [
            "id", "shopify_product_id", "title", "description", "vendor",
            "product_type", "status", "tags", "images", "variants", "synced_at",
        ]


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
    product = ProductSerializer(read_only=True)
    prompts = PromptSerializer(many=True, read_only=True)
    images = ImageSerializer(many=True, read_only=True)

    class Meta:
        model = GenerationJob
        fields = [
            "id", "product", "status", "source_images", "credits_used",
            "error_message", "prompts", "images", "created_at", "updated_at",
        ]


class CreateJobSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    source_images = serializers.ListField(child=serializers.URLField(), required=False, default=list)


class PromptInputSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    prompt = serializers.CharField(max_length=4000)
    is_selected = serializers.BooleanField(default=True)


class GenerateImagesSerializer(serializers.Serializer):
    prompts = PromptInputSerializer(many=True)


class ImageSelectionSerializer(serializers.Serializer):
    image_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)

