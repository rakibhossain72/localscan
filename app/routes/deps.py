"""
Shared dependencies: Web3 instance, Jinja2 templates, and template filters.
Import `w3` and `templates` from here in every route module.
"""
import pathlib
from datetime import datetime, timezone
from decimal import Decimal, getcontext

from fastapi.templating import Jinja2Templates

import app.indexer.config as _cfg

getcontext().prec = 50

w3 = _cfg.make_w3(_cfg.RPC_URL)

_HERE = pathlib.Path(__file__).parent.parent  # points to app/
templates = Jinja2Templates(directory=str(_HERE / "templates"))


# ---------------------------------------------------------------------------
# Jinja2 filters
# ---------------------------------------------------------------------------

def from_wei_filter(value):
    """Convert a wei integer to a human-readable ether string."""
    if value is None:
        return "0"
    try:
        human = Decimal(int(value)) / (Decimal(10) ** 18)
        return format(human.normalize(), "f")
    except (ValueError, TypeError):
        return value


def format_token_balance(value, decimals=18):
    """Convert a raw token amount to a human-readable string."""
    if value is None:
        return "0"
    try:
        human = Decimal(int(value)) / (Decimal(10) ** decimals)
        return format(human.normalize(), "f")
    except (ValueError, TypeError):
        return value


def timeago_filter(dt):
    """Return a human-readable relative time string."""
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
