import pathlib
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.routes import blocks, transactions, addresses, views
from app.indexer.background import start_indexer_thread

_APP_DIR = pathlib.Path(__file__).parent

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the indexer in background
    start_indexer_thread()
    yield
    # Shutdown: cleanup if needed

app = FastAPI(title="LocalScan Indexer API", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(_APP_DIR / "static")), name="static")

app.include_router(views.router)
app.include_router(blocks.router)
app.include_router(transactions.router)
app.include_router(addresses.router)


if __name__=="__main__":
    import uvicorn

    uvicorn.run(
        app,
    )

