"""HTML view routes for transactions."""
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Block, Contract, Token, TokenTransfer, Transaction
from app.dependencies import get_db
from app.indexer.db_service import save_block, save_transaction
from app.indexer.parser import parse_block
from app.routes.deps import templates, w3

router = APIRouter(tags=["transactions"])


def _decode_input(tx, db) -> dict | None:
    """Try to decode tx input using the to_address contract ABI. Returns decoded dict or None."""
    if not tx.to_address or not tx.input or tx.input in ("", "0x", None):
        return None
    contract = db.get(Contract, tx.to_address)
    if not contract or not contract.abi_json:
        return None
    try:
        abi = json.loads(contract.abi_json)
        w3_contract = w3.eth.contract(address=tx.to_address, abi=abi)
        raw = tx.input if tx.input.startswith("0x") else tx.input
        input_bytes = bytes.fromhex(raw.lstrip("0x"))
        fn_obj, decoded_args = w3_contract.decode_function_input(input_bytes)
        clean_args = {}
        for k, v in decoded_args.items():
            if isinstance(v, bytes):
                clean_args[k] = "0x" + v.hex()
            elif isinstance(v, (list, tuple)):
                clean_args[k] = ["0x" + i.hex() if isinstance(i, bytes) else i for i in v]
            else:
                clean_args[k] = v
        return {"function": fn_obj.fn_name, "args": clean_args}
    except Exception:  # noqa: BLE001
        return None


@router.get("/txs")
async def list_transactions(request: Request, db: Session = Depends(get_db)):
    """Render the transactions list page."""
    txs = db.execute(
        select(Transaction)
        .options(selectinload(Transaction.block))
        .order_by(desc(Transaction.block_number), desc(Transaction.tx_index))
        .limit(50)
    ).scalars().all()
    return templates.TemplateResponse("txs.html", {"request": request, "transactions": txs})


@router.get("/tx/{tx_hash}")
async def transaction_detail(request: Request, tx_hash: str, db: Session = Depends(get_db)):
    """Render the transaction detail page, fetching from chain if not yet indexed."""
    raw = tx_hash.lower()
    query_hash = raw[2:] if raw.startswith("0x") else raw

    tx = db.execute(
        select(Transaction)
        .options(selectinload(Transaction.block))
        .where(Transaction.hash == query_hash)
    ).scalar_one_or_none()

    if not tx:
        try:
            web3_tx = w3.eth.get_transaction("0x" + query_hash)
            if web3_tx:
                if not db.execute(
                    select(Block).where(Block.number == web3_tx.blockNumber)
                ).scalar_one_or_none():
                    save_block(db, parse_block(w3, web3_tx.blockNumber), w3)
                if not db.execute(
                    select(Transaction).where(Transaction.hash == query_hash)
                ).scalar_one_or_none():
                    save_transaction(db, web3_tx, web3_tx.blockNumber, web3_tx.transactionIndex, w3)
                db.commit()
                tx = db.execute(
                    select(Transaction).where(Transaction.hash == query_hash)
                ).scalar_one_or_none()
        except Exception as exc:
            print(f"Error fetching tx {tx_hash} from chain: {exc}")
            raise HTTPException(status_code=404, detail="Transaction not found") from exc

    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    tts = db.execute(
        select(TokenTransfer).where(TokenTransfer.tx_hash == query_hash)
    ).scalars().all()

    token_transfers = []
    for tt in tts:
        info = db.execute(
            select(Token).where(Token.address == tt.token_address)
        ).scalar_one_or_none()
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

    is_contract_creation = tx.contract_address is not None
    decoded_input = None if is_contract_creation else _decode_input(tx, db)

    return templates.TemplateResponse("transaction.html", {
        "request": request,
        "transaction": tx,
        "token_transfers": token_transfers,
        "is_contract_creation": is_contract_creation,
        "decoded_input": decoded_input,
    })
