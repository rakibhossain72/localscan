"""Chain state persistence — tracks the last indexed block."""
from sqlalchemy import select

from app.db.models import ChainState
import app.indexer.config as cfg


def get_chain_state(session):
    """Return (last_block_number, last_block_hash) or (-1, None) if not yet indexed."""
    stmt = select(ChainState).where(ChainState.chain_id == cfg.CHAIN_ID)
    state = session.execute(stmt).scalar_one_or_none()
    if state is None:
        return -1, None
    return state.last_block_number, state.last_block_hash


def update_chain_state(session, block_number, block_hash):
    """Upsert the chain state for the current chain ID."""
    stmt = select(ChainState).where(ChainState.chain_id == cfg.CHAIN_ID)
    state = session.execute(stmt).scalar_one_or_none()
    if state:
        state.last_block_number = block_number
        state.last_block_hash = block_hash
    else:
        state = ChainState(
            chain_id=cfg.CHAIN_ID,
            last_block_number=block_number,
            last_block_hash=block_hash,
        )
        session.add(state)
