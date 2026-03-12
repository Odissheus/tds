import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, UUIDPrimaryKey


class Promotion(UUIDPrimaryKey, Base):
    __tablename__ = "promotions"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    retailer: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    retailer_variant: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    prezzo_originale: Mapped[float] = mapped_column(Float, nullable=False)
    prezzo_promo: Mapped[float] = mapped_column(Float, nullable=False)
    sconto_percentuale: Mapped[float] = mapped_column(Float, nullable=False)
    data_inizio: Mapped[date] = mapped_column(Date, nullable=False)
    data_fine: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    url_fonte: Mapped[str] = mapped_column(String(500), nullable=False)
    promo_tag: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    settimana: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    product = relationship("Product", back_populates="promotions")

    def __repr__(self) -> str:
        return f"<Promotion {self.retailer} {self.prezzo_promo}€ ({self.sconto_percentuale}%)>"
