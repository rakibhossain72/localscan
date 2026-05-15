"""Background thread that runs the block indexer."""
import threading

from app.indexer.runner import run_indexer


def start_indexer_thread():
    """Start the indexer in a daemon thread."""
    thread = threading.Thread(target=run_indexer, daemon=True, name="chain-sniper-indexer")
    thread.start()
    print("Background indexer thread started (chain-sniper)")
    return thread
