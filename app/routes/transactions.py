"""REST API endpoints for transactions."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Transaction
from app.dependencies import get_db
from app.schemas import TransactionResponse

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("/{tx_hash}", response_model=TransactionResponse)
def get_transaction(tx_hash: str, db: Session = Depends(get_db)):
    """Return a transaction by hash."""
    query_hash = tx_hash.lower()
    if query_hash.startswith("0x"):
        query_hash = query_hash[2:]

    stmt = select(Transaction).where(Transaction.hash == query_hash)
    tx = db.execute(stmt).scalar_one_or_none()

    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return tx
