"""
Shared dependencies: Web3 instance, Jinja2 templates, and template filters.
Import `w3` and `templates` from here in every route module.
"""
from decimal import Decimal, getcontext

from fastapi.templating import Jinja2Templates
from web3 import Web3

from app.indexer.config import HTTP_RPC_URL

getcontext().prec = 50

w3 = Web3(Web3.HTTPProvider(HTTP_RPC_URL))

import pathlib
_HERE = pathlib.Path(__file__).parent.parent  # points to app/
templates = Jinja2Templates(directory=str(_HERE / "templates"))


# ---------------------------------------------------------------------------
# Jinja2 filters
# ---------------------------------------------------------------------------

def from_wei_filter(value):
    if value is None:
        return "0"
    try:
        human = Decimal(int(value)) / (Decimal(10) ** 18)
        return format(human.normalize(), "f")
    except Exception:
        return value


def format_token_balance(value, decimals=18):
    if value is None:
        return "0"
    try:
        human = Decimal(int(value)) / (Decimal(10) ** decimals)
        return format(human.normalize(), "f")
    except Exception:
        return value


def timeago_filter(dt):
    from datetime import datetime, timezone

    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    seconds = int((now - dt).total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


templates.env.filters["from_wei"] = from_wei_filter
templates.env.filters["format_token"] = format_token_balance
templates.env.filters["timeago"] = timeago_filter
