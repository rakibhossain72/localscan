import time
from web3 import Web3
from sqlalchemy import select

from app.db.models import Base, Block
from app.db.session import SessionLocal, engine
from app.indexer.config import RPC_URL, POLL_INTERVAL
from app.indexer.chain_state import get_chain_state, update_chain_state
from app.indexer.parser import parse_block
from app.indexer.db_service import save_block, save_transaction, rollback_block

def init_db():
    Base.metadata.create_all(bind=engine)

def get_session():
    return SessionLocal()

def run_indexer():
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
                    # Checking against initial genesis placeholder "0x00...00"
                    is_genesis_placeholder = (last_hash == "0x0000000000000000000000000000000000000000000000000000000000000000")
                    
                    if last_hash and not is_genesis_placeholder:
                        if block_data["parent_hash"] != last_hash:
                            print(f"Reorg detected at block {block_number}")
                            rollback_block(session, last_block)
                            last_block -= 1
                            
                            stmt = select(Block.hash).where(Block.number == last_block)
                            prev_hash = session.execute(stmt).scalar_one_or_none()
                            last_hash = prev_hash
                            
                            if not last_hash: 
                                # if we rolled back to before block 0 or state lost
                                last_hash = "0x0000000000000000000000000000000000000000000000000000000000000000"

                            update_chain_state(session, last_block, last_hash)
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

if __name__ == "__main__":
    run_indexer()
