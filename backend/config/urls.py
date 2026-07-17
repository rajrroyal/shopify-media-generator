from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    re_path(
        r"^(?P<path>(?:products|history|billing|generate(?:/[^/]+)?|generate-video(?:/[^/]+)?))/?$",
        core_views.frontend_spa_redirect,
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
