from eth_utils import to_checksum_address
from sqlalchemy import delete, select
from app.db.models import Block, Transaction, Address, Contract

def save_block(session, block_data):
    # We use merge to handle "INSERT OR REPLACE" - upsert semantics
    new_block = Block(
        number=block_data["number"],
        hash=block_data["hash"],
        parent_hash=block_data["parent_hash"],
        timestamp=block_data["timestamp"],
        miner=block_data["miner"],
        gas_used=block_data["gas_used"],
        gas_limit=block_data["gas_limit"],
        tx_count=block_data["tx_count"]
    )
    session.merge(new_block)


def save_transaction(session, tx, block_number, tx_index, w3):
    receipt = w3.eth.get_transaction_receipt(tx.hash)
    
    new_tx = Transaction(
        hash=tx.hash.hex(),
        block_number=block_number,
        tx_index=tx_index,
        from_address=to_checksum_address(tx["from"]),
        to_address=to_checksum_address(tx["to"]) if tx["to"] else None,
        value=tx["value"],
        gas=tx["gas"],
        gas_price=tx["gasPrice"],
        input=tx["input"].hex(),
        nonce=tx["nonce"],
        status=receipt.status
    )
    session.merge(new_tx)

    # ------------------
    # Address & Contract Parsing
    # ------------------
    from_addr = to_checksum_address(tx["from"])
    
    upsert_address(session, from_addr, block_number, is_contract=False)

    to_addr_raw = tx.get("to")
    if to_addr_raw:
        to_addr = to_checksum_address(to_addr_raw)
        upsert_address(session, to_addr, block_number, is_contract=False)
    else:
        # Contract Creation
        contract_address = receipt.get("contractAddress")
        if contract_address:
            c_addr = to_checksum_address(contract_address)
            upsert_address(session, c_addr, block_number, is_contract=True)

            # Save Contract Details
            new_contract = Contract(
                address=c_addr,
                creator_tx=tx.hash.hex(),
                creation_block=block_number,
                bytecode_hash=None # We'd need to fetch code to hash it
            )
            session.merge(new_contract)


def upsert_address(session, addr, block_num, is_contract=False):
    # Helper to upsert address
    # We use session.get or check existing to update flags if needed
    existing = session.get(Address, addr)
    if not existing:
        new_addr = Address(
            address=addr,
            first_seen_block=block_num,
            is_contract=is_contract,
            balance_cached=0 
        )
        session.add(new_addr)
    else:
        # Update contract flag if we just discovered it's a contract
        if is_contract and not existing.is_contract:
            existing.is_contract = True


def rollback_block(session, block_number):
    stmt_tx = delete(Transaction).where(Transaction.block_number == block_number)
    session.execute(stmt_tx)
    
    stmt_block = delete(Block).where(Block.number == block_number)
    session.execute(stmt_block)
    
    session.commit()
