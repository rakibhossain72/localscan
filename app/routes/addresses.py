from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from eth_utils import to_checksum_address
from sqlalchemy import func
from app.db.models import Address, Contract, TokenTransfer, Token
from app.dependencies import get_db
from app.schemas import AddressResponse, ContractDetails, TokenBalance

router = APIRouter(
    prefix="/addresses",
    tags=["addresses"]
)

@router.get("/{address}", response_model=AddressResponse)
def get_address(address: str, db: Session = Depends(get_db)):
    try:
        checksum_addr = to_checksum_address(address)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid address format")

    stmt = select(Address).where(Address.address == checksum_addr)
    addr_obj = db.execute(stmt).scalar_one_or_none()
    
    if not addr_obj:
        raise HTTPException(status_code=404, detail="Address not found")
        
    resp = AddressResponse(
        address=addr_obj.address,
        first_seen_block=addr_obj.first_seen_block,
        is_contract=addr_obj.is_contract,
        balance_cached=addr_obj.balance_cached,
        tokens=[]
    )
    
    if addr_obj.is_contract:
        c_stmt = select(Contract).where(Contract.address == checksum_addr)
        contract_obj = db.execute(c_stmt).scalar_one_or_none()
        if contract_obj:
            resp.contract_details = ContractDetails.model_validate(contract_obj)

    # Calculate Token Balances
    # Incoming
    incoming_stmt = (
        select(TokenTransfer.token_address, func.sum(TokenTransfer.amount))
        .where(TokenTransfer.to_address == checksum_addr)
        .group_by(TokenTransfer.token_address)
    )
    incoming = {row[0]: row[1] for row in db.execute(incoming_stmt).all()}
    
    # Outgoing
    outgoing_stmt = (
        select(TokenTransfer.token_address, func.sum(TokenTransfer.amount))
        .where(TokenTransfer.from_address == checksum_addr)
        .group_by(TokenTransfer.token_address)
    )
    outgoing = {row[0]: row[1] for row in db.execute(outgoing_stmt).all()}
    
    all_tokens = set(incoming.keys()) | set(outgoing.keys())
    
    for token_addr in all_tokens:
        balance = incoming.get(token_addr, 0) - outgoing.get(token_addr, 0)
        if balance > 0:
            # Fetch token info
            token_info = db.execute(select(Token).where(Token.address == token_addr)).scalar_one_or_none()
            resp.tokens.append(TokenBalance(
                token_address=token_addr,
                symbol=token_info.symbol if token_info else "UNK",
                decimals=token_info.decimals if token_info else 18,
                balance=balance
            ))
            
    return resp
