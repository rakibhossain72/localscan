RPC_URL = "ws://127.0.0.1:8545"
POLL_INTERVAL = 2  # seconds (used in HTTP polling mode)
CHAIN_ID = 31337   # anvil default
DB_PATH = "chain_indexer.db"  # path to the SQLite database file


def is_ws(url: str) -> bool:
    return url.startswith("ws://") or url.startswith("wss://")


def is_http(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def make_w3(url: str):
    """Return a synchronous Web3 HTTP instance for sync RPC calls (routes, deps).
    Always uses HTTP — for WS URLs, derives the HTTP equivalent.
    """
    from web3 import Web3
    if is_ws(url):
        http_url = url.replace("wss://", "https://").replace("ws://", "http://")
        return Web3(Web3.HTTPProvider(http_url))
    return Web3(Web3.HTTPProvider(url))


async def make_async_w3(url: str):
    """Return an AsyncWeb3 context manager using WebSocketProvider for ws/wss URLs.
    For http/https, returns a plain Web3 HTTPProvider (not a context manager).
    Note: only use this when you need async eth calls directly over WebSocket.
    """
    from web3 import AsyncWeb3, Web3
    from web3.providers.persistent import WebSocketProvider
    if is_ws(url):
        return AsyncWeb3(WebSocketProvider(url))
    return Web3(Web3.HTTPProvider(url))
