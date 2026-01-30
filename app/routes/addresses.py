from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from eth_utils import to_checksum_address
from app.db.models import Address, Contract
from app.dependencies import get_db
from app.schemas import AddressResponse, ContractDetails

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
        # Fallback: if address not found in DB but is valid structure, return basic info?
        # Or Just 404. Given it's an indexer API, 404 is appropriate if we haven't seen it.
        raise HTTPException(status_code=404, detail="Address not found")
        
    resp = AddressResponse(
        address=addr_obj.address,
        first_seen_block=addr_obj.first_seen_block,
        is_contract=addr_obj.is_contract,
        balance_cached=addr_obj.balance_cached
    )
    
    if addr_obj.is_contract:
        c_stmt = select(Contract).where(Contract.address == checksum_addr)
        contract_obj = db.execute(c_stmt).scalar_one_or_none()
        if contract_obj:
            resp.contract_details = ContractDetails.model_validate(contract_obj)
            
    return resp
