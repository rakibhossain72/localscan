import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.indexer.background import start_indexer_thread
from app.routes import addresses, blocks, transactions, views
from app.routes.deps import templates

_APP_DIR = pathlib.Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_indexer_thread()
    yield


app = FastAPI(title="LocalScan Indexer API", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(_APP_DIR / "static")), name="static")


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if not _wants_html(request):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    template = "404.html" if exc.status_code == 404 else "500.html"
    return templates.TemplateResponse(
        template,
        {"request": request, "detail": exc.detail},
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if not _wants_html(request):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    return templates.TemplateResponse(
        "500.html",
        {"request": request, "detail": "Invalid request parameters."},
        status_code=422,
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    if not _wants_html(request):
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    return templates.TemplateResponse(
        "500.html",
        {"request": request, "detail": None},
        status_code=500,
    )


app.include_router(views.router)
app.include_router(blocks.router)
app.include_router(transactions.router)
app.include_router(addresses.router)


if __name__=="__main__":
    import uvicorn

    uvicorn.run(
        app,
    )

