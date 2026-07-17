import json
import re
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    CreditPack,
    CreditPurchase,
    GeneratedImage,
    GeneratedPrompt,
    GeneratedVideo,
    GenerationJob,
    Shop,
    SubscriptionPlan,
)
from .serializers import (
    CreditPackSerializer,
    CreateJobSerializer,
    GenerateImagesSerializer,
    GenerateVideoSerializer,
    ImageSelectionSerializer,
    JobSerializer,
    ShopSerializer,
    SubscriptionPlanSerializer,
)
from .services.credits import refund_credit, reserve_credits, update_credit_purchase
from .services.prompts import generate_prompt_ideas
from .services.videos import complete_video, fail_video, generate_video_prompt, refresh_video, submit_video
from .services.shopify import (
    ShopifyClient,
    ShopifyReauthorizationRequired,
    build_oauth_url,
    exchange_oauth_code,
    store_shopify_tokens,
    verify_shopify_hmac,
    verify_webhook_hmac,
)
from .tasks import process_generated_image


def default_plan():
    return (
        SubscriptionPlan.objects.filter(slug="free").first()
        or SubscriptionPlan.objects.filter(is_active=True).order_by("price", "sort_order").first()
    )


def plan_for_shopify_subscription(subscription):
    name = subscription.get("name", "")
    stable_prefix = "PixelMint Plan "
    if name.startswith(stable_prefix):
        return SubscriptionPlan.objects.filter(slug=name.removeprefix(stable_prefix)).first()
    legacy_name = name.removeprefix("PixelMint ").strip()
    return SubscriptionPlan.objects.filter(slug__iexact=legacy_name).first() or (
        SubscriptionPlan.objects.filter(name__iexact=legacy_name).first()
    )


def sync_subscription_credits(shop, subscriptions):
    active = next(
        (item for item in subscriptions if item.get("status", "").upper() == "ACTIVE"),
        None,
    )
    plan = plan_for_shopify_subscription(active) if active else default_plan()
    if not plan:
        return

    now = timezone.now()
    subscription_id = active.get("id", "") if active else ""
    period_end = parse_datetime(active.get("currentPeriodEnd", "")) if active else None
    if period_end and timezone.is_naive(period_end):
        period_end = timezone.make_aware(period_end)

    plan_changed = shop.plan_id != plan.id or shop.shopify_subscription_id != subscription_id
    reset_due = (
        plan_changed
        or shop.next_plan_credit_reset_at is None
        or now >= shop.next_plan_credit_reset_at
        or (period_end and shop.next_plan_credit_reset_at != period_end)
    )
    shop.plan = plan
    shop.shopify_subscription_id = subscription_id
    update_fields = ["plan", "shopify_subscription_id"]
    if reset_due:
        shop.plan_credits_balance = plan.monthly_credits
        shop.next_plan_credit_reset_at = period_end or now + timedelta(days=30)
        update_fields.extend(["plan_credits_balance", "next_plan_credit_reset_at"])
    shop.save(update_fields=update_fields)


class MeView(APIView):
    def get(self, request):
        recent_jobs = GenerationJob.objects.filter(shop=request.user)[:5]
        shop_name = request.user.shop_domain.removesuffix(".myshopify.com").replace("-", " ").title()
        if request.user.access_token:
            try:
                context = ShopifyClient(request.user).fetch_shop_context()
                shop_data = context["shop"]
                shop_name = shop_data["name"]
                request.user.shop_domain = shop_data["myshopifyDomain"]
                sync_subscription_credits(
                    request.user,
                    context["currentAppInstallation"]["activeSubscriptions"],
                )
            except Exception:
                pass
        elif (
            request.user.next_plan_credit_reset_at is None
            or timezone.now() >= request.user.next_plan_credit_reset_at
        ):
            sync_subscription_credits(request.user, [])

        payload = ShopSerializer(request.user).data
        payload["recent_jobs"] = JobSerializer(recent_jobs, many=True, context={"request": request}).data
        payload["images_this_month"] = GeneratedImage.objects.filter(
            job__shop=request.user,
            status=GeneratedImage.Status.COMPLETED,
            created_at__year=timezone.now().year,
            created_at__month=timezone.now().month,
        ).count()
        payload["videos_this_month"] = GeneratedVideo.objects.filter(
            job__shop=request.user,
            status=GeneratedVideo.Status.COMPLETED,
            created_at__year=timezone.now().year,
            created_at__month=timezone.now().month,
        ).count()
        payload["products_enhanced"] = GenerationJob.objects.filter(
            shop=request.user,
        ).filter(
            Q(images__added_to_shopify_at__isnull=False)
            | Q(video__added_to_shopify_at__isnull=False)
        ).values("shopify_product_id").distinct().count()
        payload["shop_name"] = shop_name
        payload["credit_limit"] = request.user.plan.monthly_credits if request.user.plan else 0
        return Response(payload)


class ProductListView(APIView):
    def get(self, request):
        if not request.user.access_token:
            raise ShopifyReauthorizationRequired()
        try:
            products = ShopifyClient(request.user).fetch_products(
                request.query_params.get("search", "")
            )
        except ShopifyReauthorizationRequired:
            raise
        except Exception as exc:
            return Response({"detail": f"Could not load products from Shopify: {exc}"}, status=502)
        return Response(products)


class ProductDetailView(APIView):
    def get(self, request, product_id):
        try:
            product = ShopifyClient(request.user).fetch_product(product_id)
        except ShopifyReauthorizationRequired:
            raise
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=404)
        except Exception as exc:
            return Response({"detail": f"Could not load product from Shopify: {exc}"}, status=502)
        return Response(product)


class JobListCreateView(APIView):
    def get(self, request):
        jobs = GenerationJob.objects.filter(shop=request.user)
        return Response(JobSerializer(jobs, many=True, context={"request": request}).data)

    def post(self, request):
        serializer = CreateJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            product = ShopifyClient(request.user).fetch_product(
                serializer.validated_data["product_id"]
            )
        except ShopifyReauthorizationRequired:
            raise
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=404)
        except Exception as exc:
            return Response({"detail": f"Could not load product from Shopify: {exc}"}, status=502)
        allowed_images = {image.get("url") for image in product["images"]}
        source_images = serializer.validated_data["source_images"]
        if any(url not in allowed_images for url in source_images):
            return Response({"detail": "Reference images must belong to the selected product."}, status=400)
        job = GenerationJob.objects.create(
            shop=request.user,
            shopify_product_id=product["shopify_product_id"],
            product_data=product,
            source_images=source_images,
        )
        return Response(JobSerializer(job, context={"request": request}).data, status=201)


class JobDetailView(APIView):
    def get(self, request, job_id):
        job = get_object_or_404(
            GenerationJob.objects.prefetch_related("prompts", "images"),
            pk=job_id,
            shop=request.user,
        )
        if job.kind == GenerationJob.Kind.VIDEO and hasattr(job, "video"):
            try:
                refresh_video(job.video)
            except Exception:
                pass
        return Response(JobSerializer(job, context={"request": request}).data)


class VideoJobCreateView(APIView):
    def post(self, request):
        serializer = CreateJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            product = ShopifyClient(request.user).fetch_product(serializer.validated_data["product_id"])
        except ShopifyReauthorizationRequired:
            raise
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=404)
        except Exception as exc:
            return Response({"detail": f"Could not load product from Shopify: {exc}"}, status=502)
        allowed = {item.get("url") for item in product.get("images", [])}
        sources = serializer.validated_data["source_images"]
        if not sources:
            return Response({"detail": "Select at least one product image."}, status=400)
        if len(sources) > settings.VIDEO_MAX_REFERENCES:
            return Response({"detail": f"Select at most {settings.VIDEO_MAX_REFERENCES} images."}, status=400)
        if any(url not in allowed for url in sources):
            return Response({"detail": "Reference images must belong to the selected product."}, status=400)
        job = GenerationJob.objects.create(
            shop=request.user, shopify_product_id=product["shopify_product_id"],
            product_data=product, source_images=sources, kind=GenerationJob.Kind.VIDEO,
        )
        GeneratedVideo.objects.create(job=job)
        return Response(JobSerializer(job, context={"request": request}).data, status=201)


class GenerateVideoPromptView(APIView):
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, pk=job_id, shop=request.user, kind=GenerationJob.Kind.VIDEO)
        try:
            result = generate_video_prompt(job.product_data, job.source_images)
        except Exception as exc:
            return Response({"detail": f"Could not generate the video prompt: {exc}"}, status=502)
        video = job.video
        video.title, video.prompt = result["title"], result["prompt"]
        video.save(update_fields=["title", "prompt", "updated_at"])
        job.status = GenerationJob.Status.PROMPTS_READY
        job.save(update_fields=["status"])
        return Response(JobSerializer(job, context={"request": request}).data)


class GenerateVideoView(APIView):
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, pk=job_id, shop=request.user, kind=GenerationJob.Kind.VIDEO)
        video = job.video
        if video.status not in {GeneratedVideo.Status.DRAFT, GeneratedVideo.Status.FAILED}:
            return Response({"detail": "This video has already been submitted."}, status=409)
        serializer = GenerateVideoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cost = settings.VIDEO_GENERATION_CREDITS
        try:
            reserve_credits(job, cost, reason="AI video generation")
            video.prompt = serializer.validated_data["prompt"]
            video.settings = {
                "duration": serializer.validated_data["duration"],
                "quality": serializer.validated_data["quality"],
            }
            video.error_message = ""
            video.status = GeneratedVideo.Status.DRAFT
            video.save(update_fields=[
                "prompt", "settings", "error_message", "status", "updated_at"
            ])
            if not settings.BACKEND_URL:
                raise RuntimeError("BACKEND_URL is required for fal.ai webhooks.")
            webhook = (
                f"{settings.BACKEND_URL}/api/webhooks/fal/video/"
                f"?token={settings.FAL_WEBHOOK_SECRET}"
            )
            submit_video(video, webhook)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except Exception as exc:
            fail_video(video, exc)
            return Response({"detail": f"Could not submit video generation: {exc}"}, status=502)
        job.status = GenerationJob.Status.QUEUED
        job.save(update_fields=["status"])
        return Response(JobSerializer(job, context={"request": request}).data, status=202)


class AddVideoToShopifyView(APIView):
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, pk=job_id, shop=request.user, kind=GenerationJob.Kind.VIDEO)
        if job.video.status != GeneratedVideo.Status.COMPLETED:
            return Response({"detail": "The video is not ready."}, status=400)
        try:
            ShopifyClient(request.user).attach_video(job, job.video)
        except ShopifyReauthorizationRequired:
            raise
        except Exception as exc:
            return Response({"detail": f"Could not add video to Shopify: {exc}"}, status=502)
        return Response(JobSerializer(job, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def fal_video_webhook(request):
    if not settings.FAL_WEBHOOK_SECRET or request.query_params.get("token") != settings.FAL_WEBHOOK_SECRET:
        return Response({"detail": "Invalid webhook token."}, status=401)
    request_id = request.data.get("request_id")
    video = GeneratedVideo.objects.filter(provider_request_id=request_id).select_related("job").first()
    if not video:
        return Response({"detail": "Unknown request."}, status=404)
    try:
        complete_video(video, request.data)
    except Exception as exc:
        fail_video(video, exc)
    return Response({"ok": True})


class GeneratePromptsView(APIView):
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, pk=job_id, shop=request.user)
        try:
            prompts = generate_prompt_ideas(job.product_data, job.source_images)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except Exception:
            return Response({"detail": "Could not generate AI image prompts."}, status=502)
        job.prompts.all().delete()
        GeneratedPrompt.objects.bulk_create([
            GeneratedPrompt(
                job=job,
                title=prompt["title"],
                prompt=prompt["description"],
                sort_order=index,
            )
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

        try:
            reserve_credits(job, len(selected))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
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
            process_generated_image(image.pk)
        job.refresh_from_db()
        return Response(JobSerializer(job, context={"request": request}).data)


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
        try:
            reserve_credits(job, 1)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        replacement = GeneratedImage.objects.create(job=job, prompt=original.prompt)
        process_generated_image(replacement.pk)
        job.refresh_from_db()
        return Response(JobSerializer(job, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def oauth_launch(request):
    shop = request.query_params.get("shop", "").lower()
    if not shop.endswith(".myshopify.com"):
        return Response({"detail": "Missing or invalid shop domain."}, status=400)

    if request.query_params.get("hmac") and not verify_shopify_hmac(request.query_params):
        return Response({"detail": "Invalid Shopify signature."}, status=400)

    if Shop.objects.filter(shop_domain=shop, is_active=True).exclude(access_token="").exists():
        frontend_params = {"shop": shop, "embedded": "1"}
        if request.query_params.get("host"):
            frontend_params["host"] = request.query_params["host"]
        return HttpResponseRedirect(f"{settings.FRONTEND_URL}?{urlencode(frontend_params)}")

    url, state = build_oauth_url(shop)
    request.session["shopify_oauth_state"] = state
    request.session["shopify_oauth_host"] = request.query_params.get("host", "")
    return HttpResponseRedirect(url)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def oauth_start(request):
    shop = request.query_params.get("shop", "").lower()
    if not shop.endswith(".myshopify.com"):
        return Response({"detail": "Enter a valid myshopify.com domain."}, status=400)
    url, state = build_oauth_url(shop)
    request.session["shopify_oauth_state"] = state
    request.session["shopify_oauth_host"] = request.query_params.get("host", "")
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
    shop, _ = Shop.objects.update_or_create(
        shop_domain=shop_domain,
        defaults={
            "is_active": True,
        },
    )
    store_shopify_tokens(shop, token)
    if not shop.plan_id:
        shop.plan = default_plan()
        if shop.plan:
            shop.plan_credits_balance = shop.plan.monthly_credits
            shop.next_plan_credit_reset_at = timezone.now() + timedelta(days=30)
            shop.save(
                update_fields=["plan", "plan_credits_balance", "next_plan_credit_reset_at"]
            )
    frontend_params = {"shop": shop_domain, "embedded": "1"}
    host = request.session.pop("shopify_oauth_host", "")
    if host:
        frontend_params["host"] = host
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}?{urlencode(frontend_params)}")


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def frontend_spa_redirect(request, path):
    if path == "generate":
        resource_id = (
            request.query_params.get("id")
            or request.query_params.get("product_id")
            or request.query_params.get("ids[]")
        )
        if resource_id:
            product_id = resource_id.rstrip("/").rsplit("/", 1)[-1]
            if product_id.isdigit():
                path = f"generate/{product_id}"

    params = {
        key: request.query_params[key]
        for key in ("shop", "host", "embedded", "id_token")
        if request.query_params.get(key)
    }
    suffix = f"?{urlencode(params)}" if params else ""
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}/{path}{suffix}")


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
    plans = SubscriptionPlan.objects.filter(is_active=True)
    packs = CreditPack.objects.filter(is_active=True)
    return Response({
        "plans": SubscriptionPlanSerializer(plans, many=True).data,
        "credit_packs": CreditPackSerializer(packs, many=True).data,
    })


@api_view(["POST"])
def billing_subscribe(request):
    plan = SubscriptionPlan.objects.filter(
        slug=request.data.get("plan_id"), is_active=True
    ).first()
    if not plan or plan.price == 0:
        return Response({"detail": "Choose a paid plan."}, status=400)
    if not request.user.access_token:
        raise ShopifyReauthorizationRequired()
    mutation = """
    mutation Subscribe(
      $name: String!,
      $returnUrl: URL!,
      $lineItems: [AppSubscriptionLineItemInput!]!,
      $test: Boolean!,
      $replacementBehavior: AppSubscriptionReplacementBehavior!
    ) {
      appSubscriptionCreate(
        name: $name,
        returnUrl: $returnUrl,
        lineItems: $lineItems,
        test: $test,
        replacementBehavior: $replacementBehavior
      ) {
        appSubscription { id status test }
        confirmationUrl
        userErrors { field message }
      }
    }
    """
    return_params = {"shop": request.user.shop_domain, "embedded": "1"}
    if request.query_params.get("host"):
        return_params["host"] = request.query_params["host"]
    try:
        result = ShopifyClient(request.user).graphql(mutation, {
            "name": f"PixelMint Plan {plan.slug}",
            "returnUrl": f"{settings.FRONTEND_URL}/billing?{urlencode(return_params)}",
            "lineItems": [{"plan": {"appRecurringPricingDetails": {
                "price": {"amount": str(plan.price), "currencyCode": "USD"},
                "interval": "EVERY_30_DAYS",
            }}}],
            "test": settings.SHOPIFY_BILLING_TEST_MODE,
            "replacementBehavior": "APPLY_IMMEDIATELY",
        })["appSubscriptionCreate"]
    except ShopifyReauthorizationRequired:
        raise
    except Exception as exc:
        return Response(
            {"detail": f"Shopify billing request failed: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    if result["userErrors"]:
        message = "; ".join(error["message"] for error in result["userErrors"])
        return Response(
            {"detail": message, "errors": result["userErrors"]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not result.get("confirmationUrl"):
        return Response(
            {"detail": "Shopify did not return a billing confirmation URL."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    return Response({"confirmation_url": result["confirmationUrl"]})


@api_view(["POST"])
def billing_purchase_credits(request):
    pack = CreditPack.objects.filter(
        slug=request.data.get("pack_id"), is_active=True
    ).first()
    if not pack:
        return Response({"detail": "Choose a valid credit pack."}, status=400)
    if not request.user.access_token:
        raise ShopifyReauthorizationRequired()

    purchase = CreditPurchase.objects.create(
        shop=request.user,
        pack=pack,
        pack_name=pack.name,
        credits=pack.credits,
        amount=pack.price,
        shopify_name=f"PixelMint {pack.credits} credit pack",
    )

    return_params = {
        "shop": request.user.shop_domain,
        "embedded": "1",
        "credit_purchase": str(purchase.reference),
    }
    if request.query_params.get("host"):
        return_params["host"] = request.query_params["host"]
    mutation = """
    mutation PurchaseCredits(
      $name: String!,
      $price: MoneyInput!,
      $returnUrl: URL!,
      $test: Boolean
    ) {
      appPurchaseOneTimeCreate(
        name: $name,
        price: $price,
        returnUrl: $returnUrl,
        test: $test
      ) {
        appPurchaseOneTime { id status }
        confirmationUrl
        userErrors { field message }
      }
    }
    """
    try:
        result = ShopifyClient(request.user).graphql(mutation, {
            "name": purchase.shopify_name,
            "price": {"amount": str(pack.price), "currencyCode": "USD"},
            "returnUrl": f"{settings.FRONTEND_URL}/billing?{urlencode(return_params)}",
            "test": settings.SHOPIFY_BILLING_TEST_MODE,
        })["appPurchaseOneTimeCreate"]
    except Exception as exc:
        purchase.status = CreditPurchase.Status.ERROR
        purchase.error_message = str(exc)
        purchase.save(update_fields=["status", "error_message", "updated_at"])
        return Response({"detail": "Shopify could not create the credit purchase."}, status=502)
    if result["userErrors"]:
        purchase.status = CreditPurchase.Status.ERROR
        purchase.error_message = json.dumps(result["userErrors"])
        purchase.save(update_fields=["status", "error_message", "updated_at"])
        message = "; ".join(error["message"] for error in result["userErrors"])
        return Response(
            {"detail": message, "errors": result["userErrors"]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    purchase.shopify_purchase_id = result["appPurchaseOneTime"]["id"]
    purchase.status = result["appPurchaseOneTime"]["status"]
    purchase.save(update_fields=["shopify_purchase_id", "status", "updated_at"])
    return Response({"confirmation_url": result["confirmationUrl"]})


@api_view(["POST"])
def billing_confirm_credit_purchase(request):
    try:
        purchase = CreditPurchase.objects.get(
            shop=request.user,
            reference=request.data.get("reference"),
        )
    except (CreditPurchase.DoesNotExist, ValueError):
        return Response({"detail": "Credit purchase not found."}, status=404)
    if not purchase.shopify_purchase_id:
        return Response(
            {"detail": "Shopify has not registered this purchase yet."},
            status=status.HTTP_409_CONFLICT,
        )

    query = """
    query CreditPurchaseStatus($id: ID!) {
      node(id: $id) {
        ... on AppPurchaseOneTime { id status }
      }
    }
    """
    try:
        node = ShopifyClient(request.user).graphql(
            query,
            {"id": purchase.shopify_purchase_id},
        )["node"]
    except ShopifyReauthorizationRequired:
        raise
    except Exception:
        return Response(
            {"detail": "Could not verify the purchase with Shopify."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    if not node or node.get("id") != purchase.shopify_purchase_id:
        return Response(
            {"detail": "Shopify could not find this purchase."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    purchase = update_credit_purchase(purchase, node["status"].upper())
    request.user.refresh_from_db()
    return Response({
        "status": purchase.status,
        "credited": purchase.credited_at is not None,
        "credits_balance": request.user.credits_balance,
        "purchased_credits_balance": request.user.purchased_credits_balance,
    })


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def app_purchase_one_time_updated(request):
    if settings.SHOPIFY_API_SECRET and not verify_webhook_hmac(
        request.body, request.headers.get("X-Shopify-Hmac-Sha256", "")
    ):
        return Response({"detail": "Invalid webhook signature."}, status=401)
    try:
        data = json.loads(request.body)
        payload = data["app_purchase_one_time"]
        purchase_id = payload["admin_graphql_api_id"]
        status_value = payload["status"].upper()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return Response({"detail": "Invalid purchase webhook payload."}, status=400)

    domain = request.headers.get("X-Shopify-Shop-Domain", "")
    purchase = CreditPurchase.objects.filter(
        shop__shop_domain=domain,
        shopify_purchase_id=purchase_id,
    ).first()
    if not purchase:
        match = re.search(
            r"\[([0-9a-fA-F-]{36})\]$",
            payload.get("name", ""),
        )
        if match:
            purchase = CreditPurchase.objects.filter(
                shop__shop_domain=domain,
                reference=match.group(1),
            ).first()
            if purchase and not purchase.shopify_purchase_id:
                purchase.shopify_purchase_id = purchase_id
                purchase.save(update_fields=["shopify_purchase_id", "updated_at"])
    if not purchase:
        return Response({"detail": "Purchase is not registered yet."}, status=404)

    update_credit_purchase(purchase, status_value)
    return Response(status=status.HTTP_204_NO_CONTENT)
