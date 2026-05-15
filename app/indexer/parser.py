"""Block parsing utilities."""
from datetime import datetime
from zoneinfo import ZoneInfo


def parse_block(w3, block_number):
    """Fetch a block from the node and return a normalised dict."""
    block = w3.eth.get_block(block_number, full_transactions=True)
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
