"""Indexer configuration — patched at startup by cli.py."""
from web3 import AsyncWeb3, Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers.persistent import WebSocketProvider

RPC_URL = "ws://127.0.0.1:8545"
POLL_INTERVAL = 2  # seconds (used in HTTP polling mode)
CHAIN_ID = 31337   # anvil default
DB_PATH = "chain_indexer.db"


def is_ws(url: str) -> bool:
    """Return True if the URL uses a WebSocket scheme."""
    return url.startswith("ws://") or url.startswith("wss://")


def is_http(url: str) -> bool:
    """Return True if the URL uses an HTTP scheme."""
    return url.startswith("http://") or url.startswith("https://")


def make_w3(url: str) -> Web3:
    """Return a synchronous Web3 instance with POA middleware injected.

    For ws/wss URLs the HTTP equivalent is derived, since chain-sniper
    manages the WebSocket subscription independently.
    """
    if is_ws(url):
        http_url = url.replace("wss://", "https://").replace("ws://", "http://")
        instance = Web3(Web3.HTTPProvider(http_url))
    else:
        instance = Web3(Web3.HTTPProvider(url))
    instance.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return instance


def make_async_w3(url: str) -> AsyncWeb3:
    """Return an AsyncWeb3 context manager using WebSocketProvider for ws/wss URLs.

    For http/https URLs returns a plain synchronous Web3 instance.
    """
    if is_ws(url):
        return AsyncWeb3(WebSocketProvider(url))
    return Web3(Web3.HTTPProvider(url))
