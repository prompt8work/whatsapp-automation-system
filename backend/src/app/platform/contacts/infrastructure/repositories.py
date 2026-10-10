from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, RowMapping, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.contacts.domain.contact import Contact
from app.platform.contacts.domain.errors import ContactNotFoundError
from app.platform.contacts.domain.phone import PhoneNumber
from app.platform.contacts.infrastructure.tables import contacts
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.kernel.errors import ConcurrencyConflictError
from app.shared.kernel.ids import TenantId


def _contact(row: RowMapping) -> Contact:
    return Contact(
        id=row["id"],
        tenant_id=TenantId(row["tenant_id"]),
        phone=PhoneNumber(row["phone_e164"]),
        profile_name=row["profile_name"],
        first_seen_at=row["first_seen_at"],
        last_inbound_at=row["last_inbound_at"],
        consent_given_at=row["consent_given_at"],
        opted_out_at=row["opted_out_at"],
        version=row["version"],
    )


def _row(c: Contact) -> dict[str, Any]:
    return {
        "id": c.id,
        "tenant_id": c.tenant_id,
        "phone_e164": c.phone.e164,
        "profile_name": c.profile_name,
        "first_seen_at": c.first_seen_at,
        "last_inbound_at": c.last_inbound_at,
        "consent_given_at": c.consent_given_at,
        "opted_out_at": c.opted_out_at,
        "version": c.version,
    }


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqlContactRepository:
    def __init__(self, session: AsyncSession, uow: UnitOfWork) -> None:
        self._session, self._uow = session, uow

    async def get(self, contact_id: UUID) -> Contact:
        contact = await self._one(contacts.c.id == contact_id)
        if contact is None:
            raise ContactNotFoundError()
        return contact

    async def get_many(self, contact_ids: list[UUID]) -> list[Contact]:
        rows = await self._session.execute(select(contacts).where(contacts.c.id.in_(contact_ids)))
        return [_contact(r) for r in rows.mappings()]

    async def find_by_phone(self, phone: PhoneNumber) -> Contact | None:
        return await self._one(contacts.c.phone_e164 == phone.e164)

    async def search(self, text: str | None, *, limit: int, offset: int) -> list[Contact]:
        stmt = select(contacts)
        if text and text.strip():
            pattern = f"%{_escape_like(text.strip())}%"
            stmt = stmt.where(
                or_(
                    contacts.c.phone_e164.ilike(pattern, escape="\\"),
                    contacts.c.profile_name.ilike(pattern, escape="\\"),
                )
            )
        stmt = (
            stmt.order_by(contacts.c.last_inbound_at.desc().nulls_last(), contacts.c.id)
            .limit(limit)
            .offset(offset)
        )
        return [_contact(r) for r in (await self._session.execute(stmt)).mappings()]

    async def add(self, contact: Contact) -> bool:
        result = await self._session.execute(
            insert(contacts)
            .values(_row(contact))
            .on_conflict_do_nothing(constraint="uq_contacts_tenant_phone")
            .returning(contacts.c.id)
        )
        if result.scalar_one_or_none() is None:
            return False
        self._uow.track(contact)
        return True

    async def save(self, contact: Contact) -> None:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(contacts)
                .where(contacts.c.id == contact.id, contacts.c.version == contact.version)
                .values(_row(contact) | {"version": contact.version + 1})
            ),
        )
        if result.rowcount != 1:
            raise ConcurrencyConflictError()
        contact.version += 1
        self._uow.track(contact)

    async def _one(self, where: Any) -> Contact | None:
        row = (await self._session.execute(select(contacts).where(where))).mappings().one_or_none()
        if row is None:
            return None
        contact = _contact(row)
        self._uow.track(contact)
        return contact
