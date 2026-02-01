from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from eth_utils import to_checksum_address
from app.db.models import Address, Contract, Token, TokenBalance
from app.dependencies import get_db
from app.schemas import AddressResponse, ContractDetails, TokenBalance as TokenBalanceSchema, TokenDetails

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
        
        # Check if it's a token
        t_stmt = select(Token).where(Token.address == checksum_addr)
        token_obj = db.execute(t_stmt).scalar_one_or_none()
        if token_obj:
            resp.token_details = TokenDetails.model_validate(token_obj)

    # Fetch Token Balances from Cached Table
    tb_stmt = select(TokenBalance).where(TokenBalance.address == checksum_addr)
    balances = db.execute(tb_stmt).scalars().all()
    
    for tb in balances:
        balance_int = int(tb.balance)
        if balance_int > 0:
            # Fetch token info
            token_info = db.execute(select(Token).where(Token.address == tb.token_address)).scalar_one_or_none()
            resp.tokens.append(TokenBalanceSchema(
                token_address=tb.token_address,
                symbol=token_info.symbol if token_info else "UNK",
                decimals=token_info.decimals if token_info else 18,
                balance=balance_int
            ))
            
    return resp
