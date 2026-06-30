from django.db import migrations, models


def copy_product_data(apps, schema_editor):
    GenerationJob = apps.get_model("core", "GenerationJob")
    for job in GenerationJob.objects.select_related("product").iterator():
        product = job.product
        job.shopify_product_id = product.shopify_product_id
        job.product_data = {
            "id": product.shopify_product_id.rsplit("/", 1)[-1],
            "shopify_product_id": product.shopify_product_id,
            "title": product.title,
            "description": product.description,
            "vendor": product.vendor,
            "product_type": product.product_type,
            "status": product.status,
            "tags": product.tags,
            "images": product.images,
            "variants": product.variants,
        }
        job.save(update_fields=["shopify_product_id", "product_data"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="generationjob",
            name="shopify_product_id",
            field=models.CharField(default="", max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="generationjob",
            name="product_data",
            field=models.JSONField(default=dict),
        ),
        migrations.RunPython(copy_product_data, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="generationjob",
            name="product",
        ),
        migrations.DeleteModel(
            name="ProductSnapshot",
        ),
    ]
