from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, desc
from sqlalchemy.orm import Session, selectinload

from app.db.models import Block
from app.dependencies import get_db
from app.indexer.db_service import save_block, save_transaction
from app.indexer.parser import parse_block
from app.routes.deps import templates, w3

router = APIRouter(tags=["blocks"])


@router.get("/blocks")
async def list_blocks(request: Request, db: Session = Depends(get_db)):
    blocks = db.execute(select(Block).order_by(desc(Block.number)).limit(50)).scalars().all()
    return templates.TemplateResponse("blocks.html", {"request": request, "blocks": blocks})


@router.get("/block/{identifier}")
async def block_detail(request: Request, identifier: Union[int, str], db: Session = Depends(get_db)):
    is_hash = False
    block_number = None
    query_hash = None

    if isinstance(identifier, str):
        if identifier.isdigit():
            block_number = int(identifier)
        else:
            is_hash = True
            query_hash = identifier.lower().lstrip("0x") if identifier.lower().startswith("0x") else identifier.lower()
    else:
        block_number = identifier

    stmt = (
        select(Block)
        .options(selectinload(Block.transactions))
        .where(Block.hash == query_hash if is_hash else Block.number == block_number)
    )
    block = db.execute(stmt).scalar_one_or_none()

    if not block:
        try:
            data = parse_block(w3, identifier)
            save_block(db, data, w3)
            for i, tx in enumerate(data["transactions"]):
                save_transaction(db, tx, data["number"], i, w3)
            db.commit()
            block = db.execute(
                select(Block).options(selectinload(Block.transactions)).where(Block.number == data["number"])
            ).scalar_one_or_none()
        except Exception as e:
            print(f"Error fetching block {identifier} from chain: {e}")
            raise HTTPException(status_code=404, detail="Block not found")

    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    return templates.TemplateResponse("block.html", {"request": request, "block": block})
