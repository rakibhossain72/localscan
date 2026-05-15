from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Block, Token, TokenTransfer, Transaction
from app.dependencies import get_db
from app.indexer.db_service import save_block, save_transaction
from app.indexer.parser import parse_block
from app.routes.deps import templates, w3

router = APIRouter(tags=["transactions"])


@router.get("/txs")
async def list_transactions(request: Request, db: Session = Depends(get_db)):
    from sqlalchemy import desc

    txs = db.execute(
        select(Transaction)
        .options(selectinload(Transaction.block))
        .order_by(desc(Transaction.block_number), desc(Transaction.tx_index))
        .limit(50)
    ).scalars().all()
    return templates.TemplateResponse("txs.html", {"request": request, "transactions": txs})


@router.get("/tx/{tx_hash}")
async def transaction_detail(request: Request, tx_hash: str, db: Session = Depends(get_db)):
    query_hash = tx_hash.lower().lstrip("0x") if tx_hash.lower().startswith("0x") else tx_hash.lower()

    tx = db.execute(
        select(Transaction).options(selectinload(Transaction.block)).where(Transaction.hash == query_hash)
    ).scalar_one_or_none()

    if not tx:
        try:
            web3_tx = w3.eth.get_transaction("0x" + query_hash)
            if web3_tx:
                if not db.execute(select(Block).where(Block.number == web3_tx.blockNumber)).scalar_one_or_none():
                    save_block(db, parse_block(w3, web3_tx.blockNumber), w3)
                if not db.execute(select(Transaction).where(Transaction.hash == query_hash)).scalar_one_or_none():
                    save_transaction(db, web3_tx, web3_tx.blockNumber, web3_tx.transactionIndex, w3)
                db.commit()
                tx = db.execute(select(Transaction).where(Transaction.hash == query_hash)).scalar_one_or_none()
        except Exception as e:
            print(f"Error fetching tx {tx_hash} from chain: {e}")
            raise HTTPException(status_code=404, detail="Transaction not found")

    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    tts = db.execute(select(TokenTransfer).where(TokenTransfer.tx_hash == query_hash)).scalars().all()
    token_transfers = []
    for tt in tts:
        info = db.execute(select(Token).where(Token.address == tt.token_address)).scalar_one_or_none()
        decimals = info.decimals if info else 18
        human = Decimal(int(tt.amount)) / (Decimal(10) ** decimals)
        token_transfers.append({
            "token_address": tt.token_address,
            "token_name": info.name if info else "Unknown Token",
            "token_symbol": info.symbol if info else "UNK",
            "from": tt.from_address,
            "to": tt.to_address,
            "amount": format(human.normalize(), "f"),
            "decimals": decimals,
        })

    return templates.TemplateResponse("transaction.html", {
        "request": request,
        "transaction": tx,
        "token_transfers": token_transfers,
    })
