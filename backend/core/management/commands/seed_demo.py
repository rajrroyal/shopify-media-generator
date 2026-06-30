from django.core.management.base import BaseCommand

from core.models import Shop, SubscriptionPlan


class Command(BaseCommand):
    help = "Create a local demo shop. Catalog data always comes from Shopify."

    def handle(self, *args, **options):
        plan = SubscriptionPlan.objects.filter(slug="pro").first()
        Shop.objects.get_or_create(
            shop_domain="demo-store.myshopify.com",
            defaults={
                "plan": plan,
                "plan_credits_balance": 86,
            },
        )
        self.stdout.write(self.style.SUCCESS("Demo shop is ready."))
