"""
Route aggregator — imports all view routers and re-exports a single `router`
that main.py can include.
"""
from fastapi import APIRouter

from app.routes.home import router as home_router
from app.routes.blocks_views import router as blocks_router
from app.routes.transactions_views import router as transactions_router
from app.routes.contracts import router as contracts_router
from app.routes.tokens_views import router as tokens_router

router = APIRouter()

router.include_router(home_router)
router.include_router(blocks_router)
router.include_router(transactions_router)
router.include_router(contracts_router)
router.include_router(tokens_router)
