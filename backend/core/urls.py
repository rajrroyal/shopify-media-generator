from django.urls import path

from . import views

urlpatterns = [
    path("me/", views.MeView.as_view()),
    path("shopify/products/", views.ProductListView.as_view()),
    path("shopify/products/<str:product_id>/", views.ProductDetailView.as_view()),
    path("generation/jobs/", views.JobListCreateView.as_view()),
    path("generation/jobs/<uuid:job_id>/", views.JobDetailView.as_view()),
    path("generation/jobs/<uuid:job_id>/generate-prompts/", views.GeneratePromptsView.as_view()),
    path("generation/jobs/<uuid:job_id>/generate-images/", views.GenerateImagesView.as_view()),
    path("generation/jobs/<uuid:job_id>/images/<int:image_id>/regenerate/", views.RegenerateImageView.as_view()),
    path("generation/jobs/<uuid:job_id>/add-to-shopify/", views.AddToShopifyView.as_view()),
    path("credits/", views.MeView.as_view()),
    path("billing/plans/", views.billing_plans),
    path("billing/subscribe/", views.billing_subscribe),
    path("billing/purchase-credits/", views.billing_purchase_credits),
    path("auth/shopify/launch/", views.oauth_launch),
    path("auth/shopify/", views.oauth_start),
    path("auth/shopify/callback/", views.oauth_callback),
    path("webhooks/app-uninstalled/", views.app_uninstalled),
    path(
        "webhooks/app-purchases-one-time-update/",
        views.app_purchase_one_time_updated,
    ),
]
