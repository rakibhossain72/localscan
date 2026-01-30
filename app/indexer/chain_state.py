from sqlalchemy import select
from app.db.models import ChainState
from app.indexer.config import CHAIN_ID

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
