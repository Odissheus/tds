import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, UUIDPrimaryKey


class ScrapeStatusEnum(str, enum.Enum):
    found = "found"
    not_found = "not_found"
    error = "error"


class ScrapeLog(UUIDPrimaryKey, Base):
    __tablename__ = "scrape_logs"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    retailer: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[ScrapeStatusEnum] = mapped_column(
        Enum(ScrapeStatusEnum, name="scrape_status_enum"), nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    product = relationship("Product", back_populates="scrape_logs")

    def __repr__(self) -> str:
        return f"<ScrapeLog {self.retailer} {self.status}>"
