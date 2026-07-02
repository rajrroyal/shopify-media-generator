from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from ..models import CreditPurchase, CreditTransaction, Shop


@transaction.atomic
def reserve_credits(job, amount):
    shop = Shop.objects.select_for_update().get(pk=job.shop_id)
    if shop.credits_balance < amount:
        raise ValueError("Not enough credits")
    plan_amount = min(shop.plan_credits_balance, amount)
    purchased_amount = amount - plan_amount
    shop.plan_credits_balance -= plan_amount
    shop.purchased_credits_balance -= purchased_amount
    shop.save(update_fields=["plan_credits_balance", "purchased_credits_balance"])
    job.credits_used += amount
    job.save(update_fields=["credits_used"])
    CreditTransaction.objects.create(
        shop=shop,
        kind=CreditTransaction.Kind.DEBIT,
        amount=amount,
        plan_amount=plan_amount,
        purchased_amount=purchased_amount,
        reason="AI image generation",
        job=job,
    )


@transaction.atomic
def refund_credit(job, amount=1):
    shop = Shop.objects.select_for_update().get(pk=job.shop_id)
    allocations = CreditTransaction.objects.filter(shop=shop, job=job).aggregate(
        debited_plan=Sum("plan_amount", filter=Q(kind=CreditTransaction.Kind.DEBIT)),
        debited_purchased=Sum(
            "purchased_amount", filter=Q(kind=CreditTransaction.Kind.DEBIT)
        ),
        refunded_plan=Sum("plan_amount", filter=Q(kind=CreditTransaction.Kind.REFUND)),
        refunded_purchased=Sum(
            "purchased_amount", filter=Q(kind=CreditTransaction.Kind.REFUND)
        ),
    )
    outstanding_plan = (allocations["debited_plan"] or 0) - (
        allocations["refunded_plan"] or 0
    )
    plan_amount = min(amount, outstanding_plan)
    purchased_amount = amount - plan_amount
    shop.plan_credits_balance += plan_amount
    shop.purchased_credits_balance += purchased_amount
    shop.save(update_fields=["plan_credits_balance", "purchased_credits_balance"])
    job.credits_used = max(0, job.credits_used - amount)
    job.save(update_fields=["credits_used"])
    CreditTransaction.objects.create(
        shop=shop,
        kind=CreditTransaction.Kind.REFUND,
        amount=amount,
        plan_amount=plan_amount,
        purchased_amount=purchased_amount,
        reason="Generation failed",
        job=job,
    )


@transaction.atomic
def update_credit_purchase(purchase, status):
    """Apply a Shopify purchase update exactly once."""
    purchase = CreditPurchase.objects.select_for_update().get(pk=purchase.pk)
    purchase.status = (
        status if status in CreditPurchase.Status.values else CreditPurchase.Status.ERROR
    )
    update_fields = ["status", "updated_at"]

    if purchase.status == CreditPurchase.Status.ACTIVE and not purchase.credited_at:
        shop = Shop.objects.select_for_update().get(pk=purchase.shop_id)
        shop.purchased_credits_balance += purchase.credits
        shop.save(update_fields=["purchased_credits_balance"])
        CreditTransaction.objects.create(
            shop=shop,
            kind=CreditTransaction.Kind.CREDIT,
            amount=purchase.credits,
            purchased_amount=purchase.credits,
            reason=f"Purchased {purchase.pack_name}",
            credit_purchase=purchase,
        )
        purchase.credited_at = timezone.now()
        update_fields.append("credited_at")

    purchase.save(update_fields=update_fields)
    return purchase
