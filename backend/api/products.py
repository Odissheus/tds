"""
Products API — CRUD, suggestions, batch import.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.models.product import CategoryEnum, Product, StatusEnum

router = APIRouter(prefix="/api/products", tags=["products"])


class ProductOut(BaseModel):
    id: str
    brand: str
    series: str
    model: str
    category: str
    tier: int
    is_google: bool
    listino_eur: Optional[float]
    status: str
    not_found_streak: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    brand: str
    series: str
    model: str
    category: str
    tier: int = 1
    is_google: bool = False
    listino_eur: Optional[float] = None
    status: str = "active"


class ProductUpdate(BaseModel):
    tier: Optional[int] = None
    status: Optional[str] = None
    listino_eur: Optional[float] = None


class SuggestRequest(BaseModel):
    brand: str
    model_name_raw: str


class BatchImportRequest(BaseModel):
    text: str


class BatchImportItem(BaseModel):
    brand: str
    series: str
    model: str
    category: str
    tier: int = 1
    is_google: bool = False
    listino_eur: Optional[float] = None


class BatchConfirmRequest(BaseModel):
    products: List[BatchImportItem]


@router.get("", response_model=List[ProductOut])
async def list_products(
    brand: Optional[str] = None,
    category: Optional[str] = None,
    tier: Optional[int] = None,
    status: Optional[str] = None,
    is_google: Optional[bool] = None,
    session: AsyncSession = Depends(get_async_session),
):
    """List all products with optional filters."""
    query = select(Product)

    if brand:
        brands = [b.strip() for b in brand.split(",")]
        query = query.where(Product.brand.in_(brands))
    if category:
        query = query.where(Product.category == CategoryEnum(category))
    if tier is not None:
        query = query.where(Product.tier == tier)
    if status:
        query = query.where(Product.status == StatusEnum(status))
    if is_google is not None:
        query = query.where(Product.is_google == is_google)

    query = query.order_by(Product.brand, Product.model)
    result = await session.execute(query)
    products = result.scalars().all()

    return [
        ProductOut(
            id=str(p.id),
            brand=p.brand,
            series=p.series,
            model=p.model,
            category=p.category.value,
            tier=p.tier,
            is_google=p.is_google,
            listino_eur=p.listino_eur,
            status=p.status.value,
            not_found_streak=p.not_found_streak,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
        )
        for p in products
    ]


@router.post("", response_model=ProductOut)
async def create_product(
    data: ProductCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new product."""
    product = Product(
        brand=data.brand,
        series=data.series,
        model=data.model,
        category=CategoryEnum(data.category),
        tier=data.tier,
        is_google=data.is_google,
        listino_eur=data.listino_eur,
        status=StatusEnum(data.status),
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)

    return ProductOut(
        id=str(product.id),
        brand=product.brand,
        series=product.series,
        model=product.model,
        category=product.category.value,
        tier=product.tier,
        is_google=product.is_google,
        listino_eur=product.listino_eur,
        status=product.status.value,
        not_found_streak=product.not_found_streak,
        created_at=product.created_at.isoformat(),
        updated_at=product.updated_at.isoformat(),
    )


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: str,
    data: ProductUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    """Update product fields (tier, status, listino_eur)."""
    result = await session.execute(select(Product).where(Product.id == uuid.UUID(product_id)))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if data.tier is not None:
        product.tier = data.tier
    if data.status is not None:
        product.status = StatusEnum(data.status)
    if data.listino_eur is not None:
        product.listino_eur = data.listino_eur

    product.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(product)

    return ProductOut(
        id=str(product.id),
        brand=product.brand,
        series=product.series,
        model=product.model,
        category=product.category.value,
        tier=product.tier,
        is_google=product.is_google,
        listino_eur=product.listino_eur,
        status=product.status.value,
        not_found_streak=product.not_found_streak,
        created_at=product.created_at.isoformat(),
        updated_at=product.updated_at.isoformat(),
    )


@router.post("/suggest")
async def suggest_product(data: SuggestRequest):
    """Use AI to suggest product details."""
    from backend.agents.product_agent import suggest_product as ai_suggest

    result = ai_suggest(data.brand, data.model_name_raw)
    return result


@router.post("/import-batch")
async def import_batch_suggest(data: BatchImportRequest):
    """Use AI to parse batch product list."""
    from backend.agents.product_agent import batch_import_suggest

    result = batch_import_suggest(data.text)
    return {"products": result}


@router.post("/import-batch/confirm")
async def import_batch_confirm(
    data: BatchConfirmRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """Confirm and save batch imported products."""
    created = []
    for item in data.products:
        existing = await session.execute(
            select(Product).where(Product.brand == item.brand, Product.model == item.model)
        )
        if existing.scalar_one_or_none():
            continue

        product = Product(
            brand=item.brand,
            series=item.series,
            model=item.model,
            category=CategoryEnum(item.category),
            tier=item.tier,
            is_google=item.is_google,
            listino_eur=item.listino_eur,
            status=StatusEnum.active,
        )
        session.add(product)
        created.append(item.model)

    await session.commit()
    return {"created": len(created), "products": created}
