from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

class TransactionResponse(BaseModel):
    hash: str
    block_number: int
    tx_index: int
    from_address: str
    to_address: Optional[str]
    value: int
    gas: int
    gas_price: int
    input: Optional[str]
    nonce: int
    status: Optional[int]

    class Config:
        from_attributes = True

class BlockResponse(BaseModel):
    number: int
    hash: str
    parent_hash: str
    timestamp: datetime
    miner: str
    gas_used: int
    gas_limit: int
    tx_count: int
    transactions: List[TransactionResponse] = []

    class Config:
        from_attributes = True

class ContractDetails(BaseModel):
    creator_tx: str
    creation_block: int
    bytecode_hash: Optional[str]

    class Config:
        from_attributes = True

class AddressResponse(BaseModel):
    address: str
    first_seen_block: Optional[int]
    is_contract: bool
    balance_cached: Optional[int]
    contract_details: Optional[ContractDetails] = None

    class Config:
        from_attributes = True
