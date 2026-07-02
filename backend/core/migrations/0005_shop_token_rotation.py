from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_database_billing"),
    ]

    operations = [
        migrations.AddField(
            model_name="shop",
            name="access_token_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="shop",
            name="refresh_token",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="shop",
            name="refresh_token_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
