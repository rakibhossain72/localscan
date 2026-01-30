from fastapi import FastAPI
from app.routes import blocks, transactions

app = FastAPI(title="LocalScan Indexer API")

app.include_router(blocks.router)
app.include_router(transactions.router)

@app.get("/")
def read_root():
    return {"message": "LocalScan Indexer API is running"}
