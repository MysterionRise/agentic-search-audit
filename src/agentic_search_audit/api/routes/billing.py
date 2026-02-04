"""Billing and subscription endpoints."""

import logging
import os
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..config import APISettings, get_settings
from ..routes.auth import oauth2_scheme
from ..routes.users import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response schemas


class PlanInfo(BaseModel):
    """Subscription plan information."""

    id: str
    name: str
    price_monthly_usd: float
    audits_per_month: int
    queries_per_audit: int
    concurrent_audits: int
    features: list[str]


class SubscriptionStatus(BaseModel):
    """Current subscription status."""

    plan: PlanInfo
    status: str  # active, past_due, cancelled, trialing
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool


class CheckoutSessionRequest(BaseModel):
    """Request to create a checkout session."""

    plan_id: str = Field(description="ID of the plan to subscribe to")
    success_url: str = Field(description="URL to redirect on success")
    cancel_url: str = Field(description="URL to redirect on cancel")


class CheckoutSessionResponse(BaseModel):
    """Response with checkout session URL."""

    checkout_url: str
    session_id: str


class PortalSessionResponse(BaseModel):
    """Response with customer portal URL."""

    portal_url: str


# Available plans
PLANS = {
    "free": PlanInfo(
        id="free",
        name="Free",
        price_monthly_usd=0,
        audits_per_month=5,
        queries_per_audit=10,
        concurrent_audits=1,
        features=["Basic reports", "Email support"],
    ),
    "starter": PlanInfo(
        id="starter",
        name="Starter",
        price_monthly_usd=29,
        audits_per_month=50,
        queries_per_audit=50,
        concurrent_audits=2,
        features=[
            "All Free features",
            "Priority support",
            "API access",
            "Webhook notifications",
        ],
    ),
    "professional": PlanInfo(
        id="professional",
        name="Professional",
        price_monthly_usd=99,
        audits_per_month=200,
        queries_per_audit=100,
        concurrent_audits=5,
        features=[
            "All Starter features",
            "Advanced analytics",
            "Custom branding",
            "Team management",
            "Dedicated support",
        ],
    ),
    "enterprise": PlanInfo(
        id="enterprise",
        name="Enterprise",
        price_monthly_usd=499,
        audits_per_month=-1,  # Unlimited
        queries_per_audit=100,
        concurrent_audits=20,
        features=[
            "All Professional features",
            "Unlimited audits",
            "SLA guarantee",
            "Custom integrations",
            "Dedicated account manager",
            "On-premise option",
        ],
    ),
}


def get_stripe() -> Any:
    """Get Stripe client."""
    import stripe  # type: ignore[import-not-found]

    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing service not configured",
        )
    return stripe


@router.get("/plans", response_model=list[PlanInfo])
async def list_plans() -> list[PlanInfo]:
    """
    List available subscription plans.
    """
    return list(PLANS.values())


@router.get("/subscription", response_model=SubscriptionStatus)
async def get_subscription(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> SubscriptionStatus:
    """
    Get current subscription status.
    """
    user = await get_current_user(token, settings)

    from ...db.repositories import UserRepository  # type: ignore[import-untyped]
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = UserRepository(session)

        # Get user's Stripe customer ID
        user_data = await repo.get_by_id(user.id)
        stripe_customer_id = getattr(user_data, "stripe_customer_id", None)

        if not stripe_customer_id:
            # Return free plan for users without subscription
            return SubscriptionStatus(
                plan=PLANS["free"],
                status="active",
                current_period_start=datetime.utcnow(),
                current_period_end=datetime.utcnow(),
                cancel_at_period_end=False,
            )

        stripe = get_stripe()

        # Get active subscription
        subscriptions = stripe.Subscription.list(
            customer=stripe_customer_id,
            status="active",
            limit=1,
        )

        if not subscriptions.data:
            return SubscriptionStatus(
                plan=PLANS["free"],
                status="active",
                current_period_start=datetime.utcnow(),
                current_period_end=datetime.utcnow(),
                cancel_at_period_end=False,
            )

        subscription = subscriptions.data[0]

        # Map Stripe price to plan
        price_id = subscription["items"]["data"][0]["price"]["id"]
        plan = _get_plan_by_price_id(price_id)

        return SubscriptionStatus(
            plan=plan,
            status=subscription["status"],
            current_period_start=datetime.fromtimestamp(subscription["current_period_start"]),
            current_period_end=datetime.fromtimestamp(subscription["current_period_end"]),
            cancel_at_period_end=subscription["cancel_at_period_end"],
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.post("/checkout", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    request: CheckoutSessionRequest,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> CheckoutSessionResponse:
    """
    Create a Stripe checkout session for subscription.
    """
    if request.plan_id not in PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan ID",
        )

    if request.plan_id == "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot checkout for free plan",
        )

    user = await get_current_user(token, settings)
    stripe = get_stripe()

    from ...db.repositories import UserRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = UserRepository(session)
        user_data = await repo.get_by_id(user.id)

        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Get or create Stripe customer
        stripe_customer_id = getattr(user_data, "stripe_customer_id", None)
        if not stripe_customer_id:
            customer = stripe.Customer.create(
                email=user_data.email,
                name=user_data.name,
                metadata={"user_id": str(user.id)},
            )
            stripe_customer_id = customer.id
            # Save customer ID to user record
            await repo.update(user.id, stripe_customer_id=stripe_customer_id)

        # Get price ID for plan
        price_id = _get_price_id_for_plan(request.plan_id)

        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            customer=stripe_customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            metadata={"user_id": str(user.id), "plan_id": request.plan_id},
        )

        return CheckoutSessionResponse(
            checkout_url=checkout_session.url,
            session_id=checkout_session.id,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.post("/portal", response_model=PortalSessionResponse)
async def create_portal_session(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
    return_url: str,
) -> PortalSessionResponse:
    """
    Create a Stripe customer portal session for managing subscription.
    """
    user = await get_current_user(token, settings)
    stripe = get_stripe()

    from ...db.repositories import UserRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = UserRepository(session)
        user_data = await repo.get_by_id(user.id)

        stripe_customer_id = getattr(user_data, "stripe_customer_id", None)
        if not stripe_customer_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active subscription found",
            )

        portal_session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )

        return PortalSessionResponse(portal_url=portal_session.url)

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict[str, str]:
    """
    Handle Stripe webhook events.
    """
    stripe = get_stripe()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook not configured",
        )

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:  # type: ignore[attr-defined]
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle events
    if event["type"] == "checkout.session.completed":
        await _handle_checkout_completed(event["data"]["object"])
    elif event["type"] == "customer.subscription.updated":
        await _handle_subscription_updated(event["data"]["object"])
    elif event["type"] == "customer.subscription.deleted":
        await _handle_subscription_deleted(event["data"]["object"])
    elif event["type"] == "invoice.payment_failed":
        await _handle_payment_failed(event["data"]["object"])

    return {"status": "ok"}


async def _handle_checkout_completed(session: dict) -> None:
    """Handle successful checkout."""
    user_id = session.get("metadata", {}).get("user_id")
    plan_id = session.get("metadata", {}).get("plan_id")

    if not user_id or not plan_id:
        logger.warning("Checkout completed without user_id or plan_id metadata")
        return

    logger.info(f"Checkout completed for user {user_id}, plan {plan_id}")

    # Update user's plan in database
    from ...db.repositories import UserRepository
    from ..deps import get_db_session

    async for db_session in get_db_session():
        repo = UserRepository(db_session)
        await repo.update(UUID(user_id), plan_id=plan_id)


async def _handle_subscription_updated(subscription: dict) -> None:
    """Handle subscription update."""
    customer_id = subscription["customer"]
    status = subscription["status"]

    logger.info(f"Subscription updated for customer {customer_id}: {status}")


async def _handle_subscription_deleted(subscription: dict) -> None:
    """Handle subscription cancellation."""
    customer_id = subscription["customer"]

    logger.info(f"Subscription deleted for customer {customer_id}")

    # Downgrade to free plan
    # Note: This would need a method to find user by stripe customer ID
    # For now, this is a placeholder for future implementation
    _ = customer_id  # Placeholder until full implementation


async def _handle_payment_failed(invoice: dict) -> None:
    """Handle failed payment."""
    customer_id = invoice["customer"]

    logger.warning(f"Payment failed for customer {customer_id}")
    # Send notification email, etc.


def _get_price_id_for_plan(plan_id: str) -> str:
    """Get Stripe price ID for a plan."""
    # In production, these would be actual Stripe price IDs
    price_mapping = {
        "starter": os.getenv("STRIPE_PRICE_STARTER", "price_starter"),
        "professional": os.getenv("STRIPE_PRICE_PROFESSIONAL", "price_professional"),
        "enterprise": os.getenv("STRIPE_PRICE_ENTERPRISE", "price_enterprise"),
    }
    return price_mapping.get(plan_id, "")


def _get_plan_by_price_id(price_id: str) -> PlanInfo:
    """Get plan info by Stripe price ID."""
    # In production, this would map actual Stripe price IDs to plans
    price_to_plan = {
        os.getenv("STRIPE_PRICE_STARTER", "price_starter"): "starter",
        os.getenv("STRIPE_PRICE_PROFESSIONAL", "price_professional"): "professional",
        os.getenv("STRIPE_PRICE_ENTERPRISE", "price_enterprise"): "enterprise",
    }
    plan_id = price_to_plan.get(price_id, "free")
    return PLANS.get(plan_id, PLANS["free"])
