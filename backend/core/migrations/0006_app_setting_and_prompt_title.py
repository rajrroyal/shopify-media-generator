from django.db import migrations, models


DEFAULT_AI_IMAGES_PROMPT = """Please analyze the attached product image. The product title is: {product_title}.
You decide which scenes could be a good fit based on the product.
The product height and width is: {product_dimensions}.
Name all materials and colors precisely.
Make structured prompt suggestions for the following setups:
1. Podium/Platform
2. Splash/Action: Please use a splash that fits the product and ingredients
3. Lifestyle/Context: Mandatory: Place product on a counter or floor or table, background soft blurred
4. Nature/Outdoor/beach: Mandatory: Place product on a counter or floor or table, background soft blurred. Please choose an outdoor environment that suits the product.
5. Minimal/Studio: Please choose colors that fit the product branding.
6. Flat Lay / Top-Down: Please choose materials and ingredients that fit the product.
7. Mirror/Reflection
Output only JSON."""


def seed_ai_prompt(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    AppSetting.objects.get_or_create(
        key="ai_images_prompt",
        defaults={"value": DEFAULT_AI_IMAGES_PROMPT},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_shop_token_rotation"),
    ]

    operations = [
        migrations.CreateModel(
            name="AppSetting",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("key", models.CharField(max_length=100, unique=True)),
                ("value", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name="generatedprompt",
            name="title",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.RunPython(seed_ai_prompt, migrations.RunPython.noop),
    ]
