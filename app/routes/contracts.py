import json
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import Address, Contract, Token, TokenBalance, TokenTransfer, Transaction
from app.dependencies import get_db
from app.indexer.db_service import upsert_address
from app.routes.deps import templates, w3
from eth_utils import to_checksum_address

router = APIRouter(tags=["contracts"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_token_txs(tts, db):
    rows = []
    for tt in tts:
        info = db.execute(select(Token).where(Token.address == tt.token_address)).scalar_one_or_none()
        decimals = info.decimals if info else 18
        human = Decimal(int(tt.amount)) / (Decimal(10) ** decimals)
        rows.append({
            "tx_hash": tt.tx_hash,
            "block_number": tt.block_number,
            "token_address": tt.token_address,
            "token_symbol": info.symbol if info else "UNK",
            "from": tt.from_address,
            "to": tt.to_address,
            "amount": format(human.normalize(), "f"),
        })
    return rows


def _fmt_token_balances(balances, db):
    rows = []
    for tb in balances:
        info = db.execute(select(Token).where(Token.address == tb.token_address)).scalar_one_or_none()
        decimals = info.decimals if info else 18
        human = Decimal(int(tb.balance)) / (Decimal(10) ** decimals)
        rows.append({
            "token_address": tb.token_address,
            "symbol": info.symbol if info else "UNK",
            "decimals": decimals,
            "balance": tb.balance,
            "formatted_balance": format(human.normalize(), "f"),
        })
    return rows


async def _contract_context(request, checksum_addr, db, abi_error=None):
    """Build the full template context for contract.html."""
    addr_obj = db.execute(select(Address).where(Address.address == checksum_addr)).scalar_one_or_none()
    contract_row = db.get(Contract, checksum_addr)
    token_row = db.execute(select(Token).where(Token.address == checksum_addr)).scalar_one_or_none()

    creator_address = None
    if contract_row and contract_row.creator_tx:
        creator_tx = db.execute(
            select(Transaction).where(Transaction.hash == contract_row.creator_tx.lstrip("0x"))
        ).scalar_one_or_none()
        if creator_tx:
            creator_address = creator_tx.from_address

    txs = db.execute(
        select(Transaction)
        .where((Transaction.from_address == checksum_addr) | (Transaction.to_address == checksum_addr))
        .order_by(desc(Transaction.block_number), desc(Transaction.tx_index))
        .limit(20)
    ).scalars().all()

    tts = db.execute(
        select(TokenTransfer)
        .where((TokenTransfer.from_address == checksum_addr) | (TokenTransfer.to_address == checksum_addr))
        .order_by(desc(TokenTransfer.block_number), desc(TokenTransfer.id))
        .limit(20)
    ).scalars().all()

    balances = db.execute(select(TokenBalance).where(TokenBalance.address == checksum_addr)).scalars().all()

    return {
        "request": request,
        "address": addr_obj,
        "contract": contract_row,
        "token": token_row,
        "creator_address": creator_address,
        "transactions": txs,
        "token_transfers": _fmt_token_txs(tts, db),
        "token_balances": _fmt_token_balances(balances, db),
        "abi_error": abi_error,
    }


# ---------------------------------------------------------------------------
# Address / contract page
# ---------------------------------------------------------------------------

@router.get("/address/{address}")
async def address_detail(request: Request, address: str, db: Session = Depends(get_db)):
    try:
        checksum_addr = to_checksum_address(address)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid address format")

    addr_obj = db.execute(select(Address).where(Address.address == checksum_addr)).scalar_one_or_none()

    if not addr_obj:
        try:
            code = w3.eth.get_code(checksum_addr)
            upsert_address(db, w3, checksum_addr, w3.eth.block_number, is_contract=len(code) > 0)
            db.commit()
            addr_obj = db.execute(select(Address).where(Address.address == checksum_addr)).scalar_one_or_none()
        except Exception as e:
            print(f"Error fetching address {checksum_addr} from chain: {e}")

    if not addr_obj:
        has_tx = db.execute(
            select(Transaction)
            .where((Transaction.from_address == checksum_addr) | (Transaction.to_address == checksum_addr))
            .limit(1)
        ).scalar_one_or_none()
        if not has_tx:
            raise HTTPException(status_code=404, detail="Address not found")
        addr_obj = type("obj", (), {
            "address": checksum_addr, "is_contract": False,
            "balance_cached": 0, "first_seen_block": 0,
        })()

    if addr_obj.is_contract:
        return templates.TemplateResponse("contract.html", await _contract_context(request, checksum_addr, db))

    # EOA — build address page context
    txs = db.execute(
        select(Transaction)
        .where((Transaction.from_address == checksum_addr) | (Transaction.to_address == checksum_addr))
        .order_by(desc(Transaction.block_number), desc(Transaction.tx_index))
        .limit(20)
    ).scalars().all()

    tts = db.execute(
        select(TokenTransfer)
        .where((TokenTransfer.from_address == checksum_addr) | (TokenTransfer.to_address == checksum_addr))
        .order_by(desc(TokenTransfer.block_number), desc(TokenTransfer.id))
        .limit(20)
    ).scalars().all()

    balances = db.execute(select(TokenBalance).where(TokenBalance.address == checksum_addr)).scalars().all()

    return templates.TemplateResponse("address.html", {
        "request": request,
        "address": addr_obj,
        "token_balances": _fmt_token_balances(balances, db),
        "transactions": txs,
        "token_transfers": _fmt_token_txs(tts, db),
    })


# ---------------------------------------------------------------------------
# ABI submission
# ---------------------------------------------------------------------------

@router.post("/address/{address}/abi")
async def submit_abi(
    request: Request,
    address: str,
    abi_json: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        checksum_addr = to_checksum_address(address)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid address format")

    contract = db.get(Contract, checksum_addr)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    try:
        abi = json.loads(abi_json)
        if not isinstance(abi, list):
            raise ValueError("ABI must be a JSON array")
    except Exception as exc:
        ctx = await _contract_context(request, checksum_addr, db, abi_error=f"Invalid ABI JSON: {exc}")
        return templates.TemplateResponse("contract.html", ctx)

    try:
        w3_contract = w3.eth.contract(address=checksum_addr, abi=abi)
    except Exception as exc:
        ctx = await _contract_context(request, checksum_addr, db, abi_error=f"ABI rejected by web3: {exc}")
        return templates.TemplateResponse("contract.html", ctx)

    # Probe up to 3 no-arg view functions to confirm ABI matches on-chain contract
    view_fns = [e for e in abi if e.get("type") == "function"
                and e.get("stateMutability") in ("view", "pure")
                and not e.get("inputs")]
    errors = []
    for fn in view_fns[:3]:
        try:
            getattr(w3_contract.functions, fn["name"])().call()
        except Exception as exc:
            errors.append(str(exc))

    if view_fns and len(errors) == len(view_fns[:3]):
        ctx = await _contract_context(
            request, checksum_addr, db,
            abi_error="ABI functions could not be called on-chain. Make sure the ABI matches this contract.",
        )
        return templates.TemplateResponse("contract.html", ctx)

    contract.abi_json = json.dumps(abi)
    db.commit()
    return RedirectResponse(url=f"/address/{checksum_addr}?tab=contract", status_code=302)


# ---------------------------------------------------------------------------
# Static call
# ---------------------------------------------------------------------------

@router.post("/api/contract/{address}/call")
async def contract_call(request: Request, address: str, db: Session = Depends(get_db)):
    try:
        checksum_addr = to_checksum_address(address)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid address format")

    body = await request.json()
    fn_name: str = body.get("function")
    args: list = body.get("args", [])

    contract = db.get(Contract, checksum_addr)
    if not contract or not contract.abi_json:
        raise HTTPException(status_code=404, detail="Contract ABI not found")

    abi = json.loads(contract.abi_json)
    try:
        w3_contract = w3.eth.contract(address=checksum_addr, abi=abi)
        result = getattr(w3_contract.functions, fn_name)(*args).call()
        if isinstance(result, bytes):
            result = result.hex()
        elif isinstance(result, (list, tuple)):
            result = [r.hex() if isinstance(r, bytes) else r for r in result]
        return {"success": True, "result": result}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
