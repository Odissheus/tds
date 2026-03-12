import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, UUIDPrimaryKey


class ReportTypeEnum(str, enum.Enum):
    weekly = "weekly"
    custom = "custom"


class Report(UUIDPrimaryKey, Base):
    __tablename__ = "reports"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[ReportTypeEnum] = mapped_column(
        Enum(ReportTypeEnum, name="report_type_enum"), nullable=False
    )
    settimana: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    pdf_path: Mapped[str] = mapped_column(String(500), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_by: Mapped[str] = mapped_column(String(50), nullable=False)

    def __repr__(self) -> str:
        return f"<Report {self.title} ({self.settimana})>"
