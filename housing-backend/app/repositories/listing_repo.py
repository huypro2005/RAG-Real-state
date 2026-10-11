from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Listing


class ListingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, listing_id: str) -> Listing | None:
        stmt = (
            select(Listing)
            .options(selectinload(Listing.spatial_features))
            .where(Listing.listing_id == listing_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
