"""HTML view routes for tokens."""
from decimal import Decimal

from eth_utils import to_checksum_address
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import cast, desc, Numeric, select
from sqlalchemy.orm import Session

from app.db.models import Token, TokenBalance, TokenTransfer
from app.dependencies import get_db
from app.routes.deps import templates

router = APIRouter(tags=["tokens"])


@router.get("/token/{address}")
async def token_detail(request: Request, address: str, db: Session = Depends(get_db)):
    """Render the token detail page."""
    try:
        checksum_addr = to_checksum_address(address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid address format") from exc

    token = db.execute(
        select(Token).where(Token.address == checksum_addr)
    ).scalar_one_or_none()

    if not token:
        from app.routes.contracts import address_detail  # noqa: PLC0415
        return await address_detail(request, address, db)

    holders_objs = db.execute(
        select(TokenBalance)
        .where(TokenBalance.token_address == checksum_addr)
        .order_by(desc(cast(TokenBalance.balance, Numeric)))
        .limit(5)
    ).scalars().all()

    transfers = db.execute(
        select(TokenTransfer)
        .where(TokenTransfer.token_address == checksum_addr)
        .order_by(desc(TokenTransfer.block_number), desc(TokenTransfer.id))
        .limit(20)
    ).scalars().all()

    def _human(raw):
        d = Decimal(int(raw))
        divisor = Decimal(10) ** token.decimals if token.decimals else Decimal(1)
        return format((d / divisor).normalize(), "f")

    formatted_holders = [
        {"address": h.address, "balance": h.balance, "formatted_balance": _human(h.balance)}
        for h in holders_objs
    ]
    formatted_transfers = [
        {
            "tx_hash": t.tx_hash,
            "from_address": t.from_address,
            "to_address": t.to_address,
            "amount": t.amount,
            "formatted_amount": _human(t.amount),
        }
        for t in transfers
    ]

    return templates.TemplateResponse("token.html", {
        "request": request,
        "token": token,
        "holders": formatted_holders,
        "transfers": formatted_transfers,
    })
