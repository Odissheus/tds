import enum
from typing import Optional

from sqlalchemy import Boolean, Enum, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDPrimaryKey


class CategoryEnum(str, enum.Enum):
    smartphone = "smartphone"
    earable = "earable"
    wearable = "wearable"
    accessory = "accessory"
    bundle = "bundle"


class StatusEnum(str, enum.Enum):
    active = "active"
    eol = "eol"
    disabled = "disabled"


class Product(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "products"

    brand: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    series: Mapped[str] = mapped_column(String(200), nullable=False)
    model: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    category: Mapped[CategoryEnum] = mapped_column(
        Enum(CategoryEnum, name="category_enum"), nullable=False
    )
    tier: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_google: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    listino_eur: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[StatusEnum] = mapped_column(
        Enum(StatusEnum, name="status_enum"), nullable=False, default=StatusEnum.active
    )
    not_found_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    promotions = relationship("Promotion", back_populates="product", lazy="selectin")
    scrape_logs = relationship("ScrapeLog", back_populates="product", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Product {self.brand} {self.model} (tier={self.tier})>"
