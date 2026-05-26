# Owner B — backend/evals/rag/seed.py
#
# Seeds CMS pages for Tenant A (Bloom Florista) into the database so the RAG
# eval pipeline has realistic content to retrieve and score against.
#
# Inserts directly via SQLAlchemy — does not go through the HTTP API so it works
# even when the server is not running. Pages are marked is_published=True; chunk
# indexing must be triggered separately once the embeddings modelserver is live
# (POST /api/v1/cms/pages/{id}/publish or restart after modelserver is healthy).
#
# Usage:
#   docker compose exec backend sh -c "PYTHONPATH=/app python evals/rag/seed.py"
#
# Idempotent: skips pages whose slug already exists for Tenant A.

import asyncio
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.cms import CmsPage
from app.tenancy.rls import set_tenant_rls

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

PAGES = [
    {
        "title": "Business Hours & Location",
        "slug": "business-hours",
        "content": (
            "Bloom Florista is open Monday through Friday from 8 AM to 7 PM, "
            "Saturday from 9 AM to 6 PM, and Sunday from 10 AM to 4 PM. "
            "We are closed on all federal public holidays.\n\n"
            "Our flagship store is located at 142 Garden Street, Suite 3, downtown. "
            "Free parking is available in the adjacent lot on weekdays after 5 PM "
            "and all day on weekends.\n\n"
            "For same-day delivery orders, please place your order before 2 PM on "
            "weekdays and before 12 PM on weekends. Next-day delivery is available "
            "for orders placed by 8 PM."
        ),
        "is_published": True,
    },
    {
        "title": "Delivery & Shipping Policy",
        "slug": "delivery-policy",
        "content": (
            "Bloom Florista offers same-day delivery within a 15-mile radius of our store. "
            "Delivery is available Monday to Saturday between 9 AM and 6 PM. "
            "Sunday delivery is available for orders placed by 10 AM, delivered by 2 PM.\n\n"
            "Delivery fee: $12.99 for standard delivery. Free delivery on orders over $75. "
            "Express delivery (within 2 hours) costs an additional $8.\n\n"
            "We do not ship fresh flowers internationally. Dried flower arrangements and "
            "gift sets can be shipped nationwide with 3–5 business day transit.\n\n"
            "For wedding and event orders requiring more than 20 arrangements, please "
            "contact us at least 3 weeks in advance to confirm delivery scheduling."
        ),
        "is_published": True,
    },
    {
        "title": "Pricing & Custom Arrangements",
        "slug": "pricing",
        "content": (
            "Our bouquets start at $35 for a small hand-tied bunch and range up to $250 "
            "for our signature luxury arrangements. Custom bridal bouquets start at $120.\n\n"
            "Popular arrangements:\n"
            "- Classic Rose Dozen: $65\n"
            "- Seasonal Wildflower Bouquet: $45\n"
            "- Sunflower Delight (12 stems): $55\n"
            "- Orchid Elegance (potted): $85\n"
            "- Sympathy Wreath (large): $150\n"
            "- Wedding Table Centrepiece: $95–$180 depending on size\n\n"
            "All prices include a complimentary message card and tissue wrapping. "
            "Premium gift boxes are available for an additional $8. Corporate and bulk "
            "order discounts apply for 10 or more identical arrangements."
        ),
        "is_published": True,
    },
    {
        "title": "Wedding & Events Services",
        "slug": "wedding-events",
        "content": (
            "Bloom Florista is a full-service wedding and events florist with over 15 years "
            "of experience creating bespoke floral designs for weddings, corporate events, "
            "and private celebrations.\n\n"
            "Our wedding packages include:\n"
            "- Bridal bouquet consultation (complimentary)\n"
            "- Ceremony florals: arch, pew decorations, aisle petals\n"
            "- Reception florals: centrepieces, head table, cake flowers\n"
            "- Buttonholes, corsages, and flower girl baskets\n\n"
            "We offer a free 30-minute consultation to discuss your vision. A 25% booking "
            "deposit is required to secure your date. We accept bookings up to 18 months "
            "in advance.\n\n"
            "For corporate events we offer bespoke installations and weekly fresh-flower "
            "subscription services."
        ),
        "is_published": True,
    },
    {
        "title": "Plant Care & Frequently Asked Questions",
        "slug": "plant-care-faq",
        "content": (
            "How long will my flowers last?\n"
            "Fresh cut flowers typically last 5–10 days with proper care. Change the water "
            "every 2 days, trim the stems at a 45-degree angle, and keep the arrangement "
            "out of direct sunlight and away from fruit bowls.\n\n"
            "Can I request specific flowers?\n"
            "Yes. If a flower is in season we can usually source it within 24–48 hours. "
            "Contact us for rare or imported varieties.\n\n"
            "Do you accept returns?\n"
            "Fresh flowers are perishable and cannot be returned. If your arrangement "
            "arrives damaged, photograph it within 2 hours of delivery and contact us — "
            "we will replace it at no charge.\n\n"
            "Can I order online?\n"
            "Yes. Visit our website to browse the catalogue. Custom and wedding orders "
            "require a phone or in-store consultation.\n\n"
            "Do you have a loyalty programme?\n"
            "Yes. Every purchase earns 1 point per dollar spent. 100 points = $5 store "
            "credit. Points do not expire as long as your account is active."
        ),
        "is_published": True,
    },
    {
        "title": "Subscription & Gift Services",
        "slug": "subscriptions",
        "content": (
            "Bloom Florista offers weekly, fortnightly, and monthly fresh-flower "
            "subscriptions for homes and offices. Subscribers save 15% on every delivery "
            "and get priority scheduling during peak periods.\n\n"
            "Subscription tiers:\n"
            "- Petite (~8 stems): $30/delivery\n"
            "- Classic (~15 stems): $48/delivery\n"
            "- Luxe (large seasonal arrangement): $72/delivery\n\n"
            "Corporate subscriptions for reception and conference-room florals are available "
            "from $180/week including vase rental and weekly swap-out.\n\n"
            "Gift subscriptions make perfect presents — purchase a 3-month, 6-month, or "
            "12-month gift subscription and the recipient receives a card on each delivery. "
            "Gift subscriptions can be paused for up to 4 weeks per year for holidays."
        ),
        "is_published": True,
    },
]


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        await set_tenant_rls(session, TENANT_A)

        created = 0
        skipped = 0
        for p in PAGES:
            page = CmsPage(
                tenant_id=TENANT_A,
                title=p["title"],
                slug=p["slug"],
                content=p["content"],
                is_published=p["is_published"],
            )
            session.add(page)
            try:
                await session.flush()
                created += 1
                print(f"  created  '{p['slug']}'")
            except IntegrityError:
                await session.rollback()
                await set_tenant_rls(session, TENANT_A)
                skipped += 1
                print(f"  skipped  '{p['slug']}' (already exists)")

        await session.commit()

    await engine.dispose()
    print(f"\ndone — {created} created, {skipped} skipped.")
    print("Trigger indexing: POST /api/v1/cms/pages/{id}/publish for each page")
    print("(requires the embeddings modelserver to be running)")


if __name__ == "__main__":
    asyncio.run(main())
