"""
Indexer runner — powered by chain-sniper.

ChainSniper drives block/transaction delivery via WebSocket (eth_subscribe)
with reorg detection and automatic reconnect.  A synchronous Web3 instance
is kept alongside for the receipt / balance / call lookups that db_service needs.
"""

import asyncio
import logging
import sys
import os

from web3 import Web3
from sqlalchemy import select

# Make the chain-sniper submodule importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "chain-sniper"))

from chain_sniper import ChainSniper
from chain_sniper.filters import TransactionFilter, LogFilter

from app.db.models import Base, Block
from app.db.session import SessionLocal, engine
from app.indexer.config import RPC_URL, HTTP_RPC_URL, CHAIN_ID
from app.indexer.chain_state import get_chain_state, update_chain_state
from app.indexer.db_service import save_block, save_transaction, rollback_block

logger = logging.getLogger("indexer")


def _init_db():
    Base.metadata.create_all(bind=engine)


def _make_block_data(block) -> dict:
    """Convert a chain-sniper block (AttributeDict / dict) to the shape db_service expects."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    def _hex(val) -> str:
        """Return a lowercase hex string WITHOUT 0x prefix, matching DB storage."""
        if isinstance(val, (bytes, bytearray)):
            return val.hex()
        s = str(val)
        return s[2:] if s.startswith("0x") else s

    ts = block.get("timestamp", 0)
    dt = datetime.fromtimestamp(ts, tz=ZoneInfo("UTC"))

    return {
        "number":      block.get("number"),
        "hash":        _hex(block.get("hash")),
        "parent_hash": _hex(block.get("parentHash")),
        "timestamp":   dt,
        "miner":       block.get("miner"),
        "gas_used":    block.get("gasUsed", 0),
        "gas_limit":   block.get("gasLimit", 0),
        "tx_count":    len(block.get("transactions", [])),
        "transactions": block.get("transactions", []),
    }


async def run_indexer_async():
    _init_db()

    # Sync Web3 for receipt / balance / call lookups used by db_service
    w3 = Web3(Web3.HTTPProvider(HTTP_RPC_URL))
    while not w3.is_connected():
        logger.warning("RPC not connected, retrying...")
        await asyncio.sleep(5)
    logger.info("Connected to RPC: %s", RPC_URL)

    session = SessionLocal()
    last_block, last_hash = get_chain_state(session)
    logger.info("Resuming from block %s (hash: %s)", last_block, last_hash)

    # ------------------------------------------------------------------ #
    # chain-sniper setup
    # ------------------------------------------------------------------ #
    sniper = ChainSniper(RPC_URL, chain_id=CHAIN_ID)

    # Fetch ALL transactions in every block
    sniper.block_detail("full_block")

    # Subscribe to ERC-20 Transfer logs at the node level
    TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    log_filter = LogFilter()
    log_filter.subscribe(topics=[TRANSFER_TOPIC])
    sniper.filter(log_filter=log_filter)

    # ------------------------------------------------------------------ #
    # Callbacks
    # ------------------------------------------------------------------ #

    # Serialise block processing — one block at a time, in order.
    _process_lock = asyncio.Lock()

    def _process_block_sync(block_data: dict) -> tuple:
        """
        All blocking I/O (receipt fetches, balance calls, DB writes) runs here
        inside a thread-pool worker so the event loop is never stalled.
        Returns (new_last_block, new_last_hash, reorg: bool).
        """
        nonlocal last_block, last_hash

        block_number = block_data["number"]

        if block_number is None or block_number <= last_block:
            return last_block, last_hash, False

        genesis_placeholder = "0" * 64
        # if last_hash and last_hash != genesis_placeholder:
        #     if block_data["parent_hash"] != last_hash:
        #         logger.warning("Reorg detected at block %s", block_number)
        #         rollback_block(session, last_block)
        #         rolled_back = last_block - 1

        #         stmt = select(Block.hash).where(Block.number == rolled_back)
        #         prev_hash = session.execute(stmt).scalar_one_or_none()
        #         new_hash = prev_hash or genesis_placeholder

        #         update_chain_state(session, rolled_back, new_hash)
        #         session.commit()
        #         return rolled_back, new_hash, True

        save_block(session, block_data, w3)

        for i, tx in enumerate(block_data["transactions"]):
            save_transaction(session, tx, block_number, i, w3)

        update_chain_state(session, block_number, block_data["hash"])
        session.commit()

        logger.info("Indexed block %s  txs=%s", block_number, block_data["tx_count"])
        return block_number, block_data["hash"], False

    @sniper.on_block
    async def handle_block(block):
        nonlocal last_block, last_hash

        block_data = _make_block_data(block)
        if block_data["number"] is None or block_data["number"] <= last_block:
            return

        async with _process_lock:
            loop = asyncio.get_running_loop()
            try:
                new_lb, new_lh, _ = await loop.run_in_executor(
                    None, _process_block_sync, block_data
                )
                last_block = new_lb
                last_hash = new_lh
            except Exception as exc:
                logger.exception("Error processing block %s: %s", block_data["number"], exc)
                session.rollback()
                # Re-sync from DB so reorg detection doesn't false-positive
                # on every subsequent block after a failed commit.
                last_block, last_hash = get_chain_state(session)

    @sniper.on_reorg
    async def handle_reorg(info):
        logger.warning("Chain-sniper reorg signal: %s", info)

    @sniper.on_error
    async def handle_error(exc):
        logger.error("Chain-sniper error: %s", exc)

    # ------------------------------------------------------------------ #
    # Start
    # ------------------------------------------------------------------ #
    logger.info("Starting chain-sniper indexer (WebSocket: %s)", RPC_URL)
    await sniper.start()


def run_indexer():
    """Synchronous entry point — runs the async indexer in a new event loop."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_indexer_async())
