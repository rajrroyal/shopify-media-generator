from django.core.management.base import BaseCommand

from core.models import ProductSnapshot, Shop


PRODUCTS = [
    {
        "shopify_product_id": "gid://shopify/Product/1001",
        "title": "Aurelia Everyday Tote",
        "description": "A structured vegan leather tote with a soft suede lining and brass hardware.",
        "vendor": "Aurelia",
        "product_type": "Bags",
        "tags": ["bestseller", "vegan", "workwear"],
        "images": [{"url": "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=900"}],
        "variants": [{"title": "Cognac", "price": "129.00"}],
    },
    {
        "shopify_product_id": "gid://shopify/Product/1002",
        "title": "Cloudform Runner",
        "description": "A lightweight everyday sneaker with a sculpted sole and breathable knit upper.",
        "vendor": "Northline",
        "product_type": "Shoes",
        "tags": ["new", "unisex", "running"],
        "images": [{"url": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=900"}],
        "variants": [{"title": "Bone / 9", "price": "148.00"}],
    },
    {
        "shopify_product_id": "gid://shopify/Product/1003",
        "title": "Solis Vitamin C Serum",
        "description": "A brightening face serum with vitamin C, ferulic acid, and squalane.",
        "vendor": "Solis Lab",
        "product_type": "Skincare",
        "tags": ["clean-beauty", "vitamin-c"],
        "images": [{"url": "https://images.unsplash.com/photo-1620916566398-39f1143ab7be?w=900"}],
        "variants": [{"title": "30 ml", "price": "52.00"}],
    },
    {
        "shopify_product_id": "gid://shopify/Product/1004",
        "title": "Contour Stoneware Mug",
        "description": "Hand-finished stoneware mug with a matte glaze and comfortable rounded handle.",
        "vendor": "Common Form",
        "product_type": "Home",
        "tags": ["handmade", "kitchen"],
        "images": [{"url": "https://images.unsplash.com/photo-1514228742587-6b1558fcca3d?w=900"}],
        "variants": [{"title": "Sand", "price": "28.00"}],
    },
]


class Command(BaseCommand):
    help = "Create a local demo shop and products."

    def handle(self, *args, **options):
        shop, _ = Shop.objects.get_or_create(
            shop_domain="demo-store.myshopify.com",
            defaults={"credits_balance": 86},
        )
        for product in PRODUCTS:
            ProductSnapshot.objects.update_or_create(
                shop=shop,
                shopify_product_id=product["shopify_product_id"],
                defaults=product,
            )
        self.stdout.write(self.style.SUCCESS("Demo shop and products are ready."))

