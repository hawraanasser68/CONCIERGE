# Owner A — backend/app/repositories/widget_repo.py
#
# Widget CRUD. All queries go through scoped() so RLS + explicit WHERE both filter.
# Owner D's token exchange calls get_by_id() to validate widget_id + is_active.

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.widget import Widget
from app.repositories.base import TenantRepository


class WidgetRepository(TenantRepository[Widget]):
    model = Widget

    async def create(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        name: str,
        allowed_origins: list[str],
        greeting: str,
        persona_name: str,
    ) -> Widget:
        widget = Widget(
            tenant_id=tenant_id,
            name=name,
            allowed_origins=allowed_origins,
            greeting=greeting,
            persona_name=persona_name,
        )
        session.add(widget)
        await session.flush()
        return widget

    async def update(
        self,
        session: AsyncSession,
        widget: Widget,
        *,
        name: Optional[str] = None,
        allowed_origins: Optional[list[str]] = None,
        greeting: Optional[str] = None,
        persona_name: Optional[str] = None,
    ) -> Widget:
        if name is not None:
            widget.name = name
        if allowed_origins is not None:
            widget.allowed_origins = allowed_origins
        if greeting is not None:
            widget.greeting = greeting
        if persona_name is not None:
            widget.persona_name = persona_name
        session.add(widget)
        await session.flush()
        return widget

    async def toggle_active(self, session: AsyncSession, widget: Widget) -> Widget:
        widget.is_active = not widget.is_active
        session.add(widget)
        await session.flush()
        return widget

    async def delete(self, session: AsyncSession, widget: Widget) -> None:
        await session.delete(widget)
        await session.flush()


widget_repo = WidgetRepository()
