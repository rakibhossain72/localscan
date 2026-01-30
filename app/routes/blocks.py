from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Block
from app.dependencies import get_db
from app.schemas import BlockResponse

router = APIRouter(
    prefix="/blocks",
    tags=["blocks"]
)

@router.get("/{block_number}", response_model=BlockResponse)
def get_block(block_number: int, db: Session = Depends(get_db)):
    stmt = (
        select(Block)
        .options(selectinload(Block.transactions))
        .where(Block.number == block_number)
    )
    block = db.execute(stmt).scalar_one_or_none()
    
    if block is None:
        raise HTTPException(status_code=404, detail="Block not found")
        
    return block
