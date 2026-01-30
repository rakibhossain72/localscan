import time
from datetime import datetime
from zoneinfo import ZoneInfo
from web3 import Web3
from eth_utils import to_checksum_address
from sqlalchemy import select, delete

from app.db.session import SessionLocal, engine
from app.db.models import Base, ChainState, Block, Transaction

RPC_URL = "http://127.0.0.1:8545"
POLL_INTERVAL = 1  # seconds
CHAIN_ID = 31337   # anvil default


# --------------------
# DB SETUP
# --------------------

def init_db():
    Base.metadata.create_all(bind=engine)

def get_session():
    return SessionLocal()


def get_chain_state(session):
    stmt = select(ChainState).where(ChainState.chain_id == CHAIN_ID)
    state = session.execute(stmt).scalar_one_or_none()

    if state is None:
        return -1, None

    return state.last_block_number, state.last_block_hash


def update_chain_state(session, block_number, block_hash):
    stmt = select(ChainState).where(ChainState.chain_id == CHAIN_ID)
    state = session.execute(stmt).scalar_one_or_none()
    
    if state:
        state.last_block_number = block_number
        state.last_block_hash = block_hash
    else:
        state = ChainState(
            chain_id=CHAIN_ID,
            last_block_number=block_number,
            last_block_hash=block_hash
        )
        session.add(state)
    # updated_at is auto-updated by onupdate=func.now() in model


# --------------------
# PARSERS
# --------------------

def parse_block(w3, block_number):
    block = w3.eth.get_block(block_number, full_transactions=True)

    # Convert timestamp to datetime aware
    dt = datetime.fromtimestamp(block.timestamp, tz=ZoneInfo("UTC"))

    return {
        "number": block.number,
        "hash": block.hash.hex(),
        "parent_hash": block.parentHash.hex(),
        "timestamp": dt,
        "miner": block.miner,
        "gas_used": block.gasUsed,
        "gas_limit": block.gasLimit,
        "tx_count": len(block.transactions),
        "transactions": block.transactions,
    }


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


# --------------------
# REORG HANDLING
# --------------------

def rollback_block(session, block_number):
    # Cascades should handle transactions if ForeignKey ondelete='CASCADE' is respected,
    # but manually deleting is safe.
    session.execute(delete(Transaction).where(Transaction.block_number == block_number))
    session.execute(delete(Block).where(Block.number == block_number))
    session.commit()


# --------------------
# MAIN LOOP
# --------------------

if __name__ == "__main__":
    init_db()
    
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    
    # Wait for RPC connection
    connected = False
    while not connected:
        if w3.is_connected():
            connected = True
        else:
            print("RPC not connected, retrying...")
            time.sleep(5)
            # Re-instantiate provider potentially? Not needed for HTTP usually.

    session = get_session()
    try:
        last_block, last_hash = get_chain_state(session)
        print(f"Indexer started at block {last_block} (Hash: {last_hash})")

        while True:
            try:
                latest = w3.eth.block_number

                if latest <= last_block:
                    time.sleep(POLL_INTERVAL)
                    continue

                for block_number in range(last_block + 1, latest + 1):
                    block_data = parse_block(w3, block_number)
                    
                    # reorg check
                    if last_hash and last_hash != "0x0000000000000000000000000000000000000000000000000000000000000000":
                        if block_data["parent_hash"] != last_hash:
                            print(f"Reorg detected at block {block_number}")
                            rollback_block(session, last_block)
                            last_block -= 1
                            
                            stmt = select(Block.hash).where(Block.number == last_block)
                            prev_hash = session.execute(stmt).scalar_one_or_none()
                            last_hash = prev_hash
                            
                            update_chain_state(session, last_block, last_hash if last_hash else "0x0000000000000000000000000000000000000000000000000000000000000000")
                            session.commit()
                            break

                    save_block(session, block_data)

                    for i, tx in enumerate(block_data["transactions"]):
                        save_transaction(session, tx, block_number, i, w3)

                    update_chain_state(session, block_number, block_data["hash"])
                    session.commit()

                    last_block = block_number
                    last_hash = block_data["hash"]

                    print(f"Indexed block {block_number}")

            except Exception as e:
                print("Indexer error:", e)
                session.rollback()
                time.sleep(2)
    finally:
        session.close()
