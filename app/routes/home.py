from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, desc
from sqlalchemy.orm import Session, selectinload

from app.db.models import Block, Transaction
from app.dependencies import get_db
from app.routes.deps import templates

router = APIRouter(tags=["home"])


@router.get("/")
async def index(request: Request, db: Session = Depends(get_db)):
    blocks = db.execute(select(Block).order_by(desc(Block.number)).limit(10)).scalars().all()
    txs = db.execute(
        select(Transaction)
        .options(selectinload(Transaction.block))
        .order_by(desc(Transaction.block_number), desc(Transaction.tx_index))
        .limit(10)
    ).scalars().all()
    return templates.TemplateResponse("index.html", {"request": request, "blocks": blocks, "transactions": txs})


@router.get("/api/docs")
async def api_docs(request: Request):
    return templates.TemplateResponse("api_docs.html", {"request": request})


@router.get("/search")
async def search(request: Request, q: str, db: Session = Depends(get_db)):
    from app.routes.blocks_views import block_detail
    from app.routes.transactions_views import transaction_detail
    from app.routes.contracts import address_detail
    from fastapi import HTTPException

    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "Search query is empty"})

    q = q.strip()

    if q.isdigit():
        return await block_detail(request, int(q), db)

    clean = q.lower()
    addr_part = clean[2:] if clean.startswith("0x") else clean

    if len(addr_part) == 40:
        try:
            return await address_detail(request, q, db)
        except HTTPException:
            pass

    hash_part = clean[2:] if clean.startswith("0x") else clean
    if len(hash_part) == 64:
        try:
            return await transaction_detail(request, q, db)
        except HTTPException:
            try:
                return await block_detail(request, q, db)
            except HTTPException:
                pass

    return templates.TemplateResponse("index.html", {
        "request": request,
        "error": f"No results found for '{q}'",
        "blocks": [],
        "transactions": [],
    })
