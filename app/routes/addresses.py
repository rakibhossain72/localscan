"""REST API endpoints for addresses."""
from eth_utils import to_checksum_address
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Address, Contract, Token, TokenBalance
from app.dependencies import get_db
from app.schemas import (
    AddressResponse,
    ContractDetails,
    TokenBalance as TokenBalanceSchema,
    TokenDetails,
)

router = APIRouter(prefix="/addresses", tags=["addresses"])


@router.get("/{address}", response_model=AddressResponse)
def get_address(address: str, db: Session = Depends(get_db)):
    """Return address details including contract and token info."""
    try:
        checksum_addr = to_checksum_address(address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid address format") from exc

    stmt = select(Address).where(Address.address == checksum_addr)
    addr_obj = db.execute(stmt).scalar_one_or_none()

    if not addr_obj:
        raise HTTPException(status_code=404, detail="Address not found")

    resp = AddressResponse(
        address=addr_obj.address,
        first_seen_block=addr_obj.first_seen_block,
        is_contract=addr_obj.is_contract,
        balance_cached=addr_obj.balance_cached,
        tokens=[],
    )

    if addr_obj.is_contract:
        contract_obj = db.execute(
            select(Contract).where(Contract.address == checksum_addr)
        ).scalar_one_or_none()
        if contract_obj:
            resp.contract_details = ContractDetails.model_validate(contract_obj)

        token_obj = db.execute(
            select(Token).where(Token.address == checksum_addr)
        ).scalar_one_or_none()
        if token_obj:
            resp.token_details = TokenDetails.model_validate(token_obj)

    balances = db.execute(
        select(TokenBalance).where(TokenBalance.address == checksum_addr)
    ).scalars().all()

    for tb in balances:
        balance_int = int(tb.balance)
        if balance_int > 0:
            token_info = db.execute(
                select(Token).where(Token.address == tb.token_address)
            ).scalar_one_or_none()
            resp.tokens.append(TokenBalanceSchema(
                token_address=tb.token_address,
                symbol=token_info.symbol if token_info else "UNK",
                decimals=token_info.decimals if token_info else 18,
                balance=balance_int,
            ))

    return resp
