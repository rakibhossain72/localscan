"""
Indexer runner — supports both WebSocket (ws/wss) and HTTP/HTTPS RPC endpoints.

- ws/wss  → chain-sniper drives block delivery via eth_subscribe
- http/https → polling loop fetches new blocks on POLL_INTERVAL
"""
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import app.indexer.config as cfg
from app.db.models import Base
from app.db.session import SessionLocal, engine
from app.indexer.chain_state import get_chain_state, update_chain_state
from app.indexer.config import is_ws, make_w3
from app.indexer.db_service import save_block, save_transaction

logger = logging.getLogger("indexer")

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _init_db():
    Base.metadata.create_all(bind=engine)


def _make_block_data(block) -> dict:
    """Convert a chain-sniper block (AttributeDict / dict) to the shape db_service expects."""
    def _hex(val) -> str:
        if isinstance(val, (bytes, bytearray)):
            return val.hex()
        s = str(val)
        return s[2:] if s.startswith("0x") else s

    ts = block.get("timestamp", 0)
    dt = datetime.fromtimestamp(ts, tz=ZoneInfo("UTC"))

    return {
        "number":       block.get("number"),
        "hash":         _hex(block.get("hash")),
        "parent_hash":  _hex(block.get("parentHash")),
        "timestamp":    dt,
        "miner":        block.get("miner"),
        "gas_used":     block.get("gasUsed", 0),
        "gas_limit":    block.get("gasLimit", 0),
        "tx_count":     len(block.get("transactions", [])),
        "transactions": block.get("transactions", []),
    }


# ---------------------------------------------------------------------------
# Shared block processor
# ---------------------------------------------------------------------------

def _process_block_sync(session, w3, block_data: dict, last_block: int, last_hash: str):
    """Write a block and its transactions to the DB. Returns (new_last_block, new_last_hash)."""
    block_number = block_data["number"]
    if block_number is None or block_number <= last_block:
        return last_block, last_hash

    save_block(session, block_data, w3)
    for i, tx in enumerate(block_data["transactions"]):
        save_transaction(session, tx, block_number, i, w3)

    update_chain_state(session, block_number, block_data["hash"])
    session.commit()

    logger.info("Indexed block %s  txs=%s", block_number, block_data["tx_count"])
    return block_number, block_data["hash"]


# ---------------------------------------------------------------------------
# WebSocket mode — chain-sniper for subscriptions, sync w3 for data fetching
# ---------------------------------------------------------------------------

async def _run_ws(session):
    """Run the indexer using chain-sniper WebSocket subscriptions."""
    from chain_sniper import ChainSniper
    from chain_sniper.filters import LogFilter

    w3 = make_w3(cfg.RPC_URL)
    while not w3.is_connected():
        logger.warning("RPC not connected, retrying in 5s...")
        await asyncio.sleep(5)
    logger.info("Connected to RPC: %s", cfg.RPC_URL)

    last_block, last_hash = get_chain_state(session)
    logger.info("WS mode — resuming from block %s", last_block)

    sniper = ChainSniper(cfg.RPC_URL, chain_id=cfg.CHAIN_ID)
    sniper.block_detail("full_block")

    log_filter = LogFilter()
    log_filter.subscribe(topics=[TRANSFER_TOPIC])
    sniper.filter(log_filter=log_filter)

    _process_lock = asyncio.Lock()

    @sniper.on_block
    async def handle_block(block):
        nonlocal last_block, last_hash
        block_data = _make_block_data(block)
        if block_data["number"] is None or block_data["number"] <= last_block:
            return
        async with _process_lock:
            loop = asyncio.get_running_loop()
            try:
                new_lb, new_lh = await loop.run_in_executor(
                    None, _process_block_sync, session, w3, block_data, last_block, last_hash
                )
                last_block, last_hash = new_lb, new_lh
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error processing block %s: %s", block_data["number"], exc)
                session.rollback()
                last_block, last_hash = get_chain_state(session)

    @sniper.on_reorg
    async def handle_reorg(info):
        logger.warning("Reorg signal: %s", info)

    @sniper.on_error
    async def handle_error(exc):
        logger.error("Chain-sniper error: %s", exc)

    logger.info("Starting chain-sniper indexer (WS: %s)", cfg.RPC_URL)
    await sniper.start()


# ---------------------------------------------------------------------------
# HTTP polling mode
# ---------------------------------------------------------------------------

async def _run_http(w3, session):
    """Run the indexer by polling eth_blockNumber on an interval."""
    last_block, last_hash = get_chain_state(session)
    logger.info(
        "HTTP polling mode — resuming from block %s (interval: %ss)",
        last_block,
        cfg.POLL_INTERVAL,
    )

    _process_lock = asyncio.Lock()

    while True:
        try:
            loop = asyncio.get_running_loop()
            latest = await loop.run_in_executor(None, lambda: w3.eth.block_number)

            if latest > last_block:
                for num in range(last_block + 1, latest + 1):
                    block = await loop.run_in_executor(
                        None, lambda n=num: w3.eth.get_block(n, full_transactions=True)
                    )
                    block_data = _make_block_data(block)
                    async with _process_lock:
                        try:
                            last_block, last_hash = await loop.run_in_executor(
                                None,
                                _process_block_sync,
                                session,
                                w3,
                                block_data,
                                last_block,
                                last_hash,
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.exception("Error processing block %s: %s", num, exc)
                            session.rollback()
                            last_block, last_hash = get_chain_state(session)
                            break

        except Exception as exc:  # noqa: BLE001
            logger.error("Polling error: %s", exc)

        await asyncio.sleep(cfg.POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

async def run_indexer_async():
    """Async entry point — selects WS or HTTP mode based on the RPC URL scheme."""
    _init_db()
    session = SessionLocal()

    if is_ws(cfg.RPC_URL):
        await _run_ws(session)
    else:
        w3 = make_w3(cfg.RPC_URL)
        while not w3.is_connected():
            logger.warning("RPC not connected, retrying in 5s...")
            await asyncio.sleep(5)
        logger.info("Connected to RPC: %s", cfg.RPC_URL)
        await _run_http(w3, session)


def run_indexer():
    """Synchronous entry point — runs the async indexer in a new event loop."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_indexer_async())
