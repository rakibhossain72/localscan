import threading
from app.indexer.runner import run_indexer

def run_indexer_background():
    """Run the indexer in a background thread"""
    run_indexer()

def start_indexer_thread():
    """Start the indexer in a daemon thread"""
    indexer_thread = threading.Thread(target=run_indexer_background, daemon=True)
    indexer_thread.start()
    print("Background indexer thread started")
    return indexer_thread
