from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import GeneratedImage, GeneratedPrompt, GenerationJob, ProductSnapshot, Shop
from .serializers import (
    CreateJobSerializer,
    GenerateImagesSerializer,
    ImageSelectionSerializer,
    JobSerializer,
    ProductSerializer,
    ShopSerializer,
)
from .services import (
    ShopifyClient,
    build_oauth_url,
    exchange_oauth_code,
    generate_prompt_ideas,
    reserve_credits,
    verify_shopify_hmac,
    verify_webhook_hmac,
)
from .tasks import generate_image_task


PLANS = [
    {"id": "free", "name": "Free", "price": 0, "credits": 10, "description": "Try PixelMint on a few products."},
    {"id": "starter", "name": "Starter", "price": 9, "credits": 100, "description": "For new and growing storefronts."},
    {"id": "pro", "name": "Pro", "price": 29, "credits": 400, "description": "For active brands publishing weekly.", "featured": True},
    {"id": "growth", "name": "Growth", "price": 79, "credits": 1500, "description": "For teams and larger catalogs."},
]


class MeView(APIView):
    def get(self, request):
        recent_jobs = GenerationJob.objects.filter(shop=request.user)[:5]
        payload = ShopSerializer(request.user).data
        payload["recent_jobs"] = JobSerializer(recent_jobs, many=True, context={"request": request}).data
        payload["images_this_month"] = GeneratedImage.objects.filter(
            job__shop=request.user,
            status=GeneratedImage.Status.COMPLETED,
            created_at__year=timezone.now().year,
            created_at__month=timezone.now().month,
        ).count()
        return Response(payload)


class ProductListView(APIView):
    def get(self, request):
        products = ProductSnapshot.objects.filter(shop=request.user)
        search = request.query_params.get("search")
        if search:
            products = products.filter(title__icontains=search)
        return Response(ProductSerializer(products, many=True).data)

    def post(self, request):
        if not request.user.access_token:
            return Response({"detail": "Connect a Shopify store before syncing."}, status=400)
        ShopifyClient(request.user).sync_products()
        products = ProductSnapshot.objects.filter(shop=request.user)
        return Response(ProductSerializer(products, many=True).data)


class ProductDetailView(APIView):
    def get(self, request, pk):
        product = get_object_or_404(ProductSnapshot, pk=pk, shop=request.user)
        return Response(ProductSerializer(product).data)


class JobListCreateView(APIView):
    def get(self, request):
        jobs = GenerationJob.objects.filter(shop=request.user).select_related("product")
        return Response(JobSerializer(jobs, many=True, context={"request": request}).data)

    def post(self, request):
        serializer = CreateJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = get_object_or_404(
            ProductSnapshot,
            pk=serializer.validated_data["product_id"],
            shop=request.user,
        )
        job = GenerationJob.objects.create(
            shop=request.user,
            product=product,
            source_images=serializer.validated_data["source_images"],
        )
        return Response(JobSerializer(job, context={"request": request}).data, status=201)


class JobDetailView(APIView):
    def get(self, request, job_id):
        job = get_object_or_404(
            GenerationJob.objects.select_related("product").prefetch_related("prompts", "images"),
            pk=job_id,
            shop=request.user,
        )
        return Response(JobSerializer(job, context={"request": request}).data)


class GeneratePromptsView(APIView):
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, pk=job_id, shop=request.user)
        prompts = generate_prompt_ideas(job.product)
        job.prompts.all().delete()
        GeneratedPrompt.objects.bulk_create([
            GeneratedPrompt(job=job, prompt=prompt, sort_order=index)
            for index, prompt in enumerate(prompts)
        ])
        job.status = GenerationJob.Status.PROMPTS_READY
        job.save(update_fields=["status"])
        return Response(JobSerializer(job, context={"request": request}).data)


class GenerateImagesView(APIView):
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, pk=job_id, shop=request.user)
        serializer = GenerateImagesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        selected = [item for item in serializer.validated_data["prompts"] if item["is_selected"]]
        if not selected:
            return Response({"detail": "Select at least one prompt."}, status=400)

        reserve_credits(job, len(selected))
        images = []
        for index, item in enumerate(selected):
            prompt = None
            if item.get("id"):
                prompt = job.prompts.filter(pk=item["id"]).first()
            if prompt:
                prompt.prompt = item["prompt"]
                prompt.is_selected = True
                prompt.save(update_fields=["prompt", "is_selected"])
            else:
                prompt = GeneratedPrompt.objects.create(
                    job=job, prompt=item["prompt"], is_selected=True, sort_order=index
                )
            images.append(GeneratedImage.objects.create(job=job, prompt=prompt))

        job.status = GenerationJob.Status.QUEUED
        job.save(update_fields=["status"])
        for image in images:
            generate_image_task.delay(image.pk)
        return Response(JobSerializer(job, context={"request": request}).data, status=202)


class AddToShopifyView(APIView):
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, pk=job_id, shop=request.user)
        serializer = ImageSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        images = list(job.images.filter(
            pk__in=serializer.validated_data["image_ids"],
            status=GeneratedImage.Status.COMPLETED,
        ))
        if not images:
            return Response({"detail": "Select at least one completed image."}, status=400)
        if not request.user.access_token:
            return Response({"detail": "Shopify is not connected in demo mode."}, status=400)
        ShopifyClient(request.user).attach_images(job, images)
        return Response(JobSerializer(job, context={"request": request}).data)


class RegenerateImageView(APIView):
    def post(self, request, job_id, image_id):
        job = get_object_or_404(GenerationJob, pk=job_id, shop=request.user)
        original = get_object_or_404(job.images, pk=image_id)
        reserve_credits(job, 1)
        replacement = GeneratedImage.objects.create(job=job, prompt=original.prompt)
        generate_image_task.delay(replacement.pk)
        return Response(JobSerializer(job, context={"request": request}).data, status=202)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def oauth_launch(request):
    shop = request.query_params.get("shop", "").lower()
    if not shop.endswith(".myshopify.com"):
        return Response({"detail": "Missing or invalid shop domain."}, status=400)

    if request.query_params.get("hmac") and not verify_shopify_hmac(request.query_params):
        return Response({"detail": "Invalid Shopify signature."}, status=400)

    if Shop.objects.filter(shop_domain=shop, is_active=True).exclude(access_token="").exists():
        return HttpResponseRedirect(f"{settings.FRONTEND_URL}?{urlencode({'shop': shop})}")

    url, state = build_oauth_url(shop)
    request.session["shopify_oauth_state"] = state
    return HttpResponseRedirect(url)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def oauth_start(request):
    shop = request.query_params.get("shop", "").lower()
    if not shop.endswith(".myshopify.com"):
        return Response({"detail": "Enter a valid myshopify.com domain."}, status=400)
    url, state = build_oauth_url(shop)
    request.session["shopify_oauth_state"] = state
    return HttpResponseRedirect(url)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def oauth_callback(request):
    if request.query_params.get("state") != request.session.get("shopify_oauth_state"):
        return Response({"detail": "Invalid OAuth state."}, status=400)
    if not verify_shopify_hmac(request.query_params):
        return Response({"detail": "Invalid Shopify signature."}, status=400)
    shop_domain = request.query_params["shop"]
    token = exchange_oauth_code(shop_domain, request.query_params["code"])
    Shop.objects.update_or_create(
        shop_domain=shop_domain,
        defaults={
            "access_token": token["access_token"],
            "scope": token.get("scope", ""),
            "is_active": True,
        },
    )
    frontend_params = {"shop": shop_domain}
    host = request.query_params.get("host")
    if host:
        frontend_params["host"] = host
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}?{urlencode(frontend_params)}")


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def app_uninstalled(request):
    if settings.SHOPIFY_API_SECRET and not verify_webhook_hmac(
        request.body, request.headers.get("X-Shopify-Hmac-Sha256", "")
    ):
        return Response({"detail": "Invalid webhook signature."}, status=401)
    domain = request.headers.get("X-Shopify-Shop-Domain")
    if domain:
        Shop.objects.filter(shop_domain=domain).update(is_active=False, access_token="")
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def billing_plans(request):
    return Response(PLANS)


@api_view(["POST"])
def billing_subscribe(request):
    plan = next((plan for plan in PLANS if plan["id"] == request.data.get("plan_id")), None)
    if not plan or plan["price"] == 0:
        return Response({"detail": "Choose a paid plan."}, status=400)
    if not request.user.access_token:
        return Response({"detail": "Connect Shopify before subscribing."}, status=400)
    mutation = """
    mutation Subscribe($name: String!, $returnUrl: URL!, $lineItems: [AppSubscriptionLineItemInput!]!) {
      appSubscriptionCreate(name: $name, returnUrl: $returnUrl, lineItems: $lineItems) {
        confirmationUrl
        userErrors { field message }
      }
    }
    """
    result = ShopifyClient(request.user).graphql(mutation, {
        "name": f"PixelMint {plan['name']}",
        "returnUrl": f"{settings.FRONTEND_URL}/billing",
        "lineItems": [{"plan": {"appRecurringPricingDetails": {
            "price": {"amount": plan["price"], "currencyCode": "USD"},
            "interval": "EVERY_30_DAYS",
        }}}],
    })["appSubscriptionCreate"]
    if result["userErrors"]:
        return Response({"errors": result["userErrors"]}, status=400)
    return Response({"confirmation_url": result["confirmationUrl"]})
