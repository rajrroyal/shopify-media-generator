import django.db.models.deletion
import core.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0006_app_setting_and_prompt_title")]

    operations = [
        migrations.AddField(
            model_name="generationjob",
            name="kind",
            field=models.CharField(
                choices=[("image", "Image"), ("video", "Video")],
                default="image",
                max_length=10,
            ),
        ),
        migrations.CreateModel(
            name="GeneratedVideo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, max_length=120)),
                ("prompt", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("queued", "Queued"), ("processing", "Processing"), ("completed", "Completed"), ("failed", "Failed")], default="draft", max_length=20)),
                ("model_id", models.CharField(blank=True, max_length=255)),
                ("provider_request_id", models.CharField(blank=True, db_index=True, max_length=255)),
                ("provider_video_url", models.URLField(blank=True, max_length=2000)),
                ("video", models.FileField(blank=True, upload_to=core.models.generated_video_path)),
                ("thumbnail_url", models.URLField(blank=True, max_length=2000)),
                ("settings", models.JSONField(default=dict)),
                ("provider_metadata", models.JSONField(default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("shopify_media_id", models.CharField(blank=True, max_length=255)),
                ("shopify_status", models.CharField(blank=True, max_length=30)),
                ("added_to_shopify_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("job", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="video", to="core.generationjob")),
            ],
        ),
    ]
