from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from eth_utils import to_checksum_address

from app.db.models import Block, Transaction, Address, Contract, Token, TokenBalance
from app.dependencies import get_db

router = APIRouter(tags=["views"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/blocks")
async def list_blocks(request: Request, db: Session = Depends(get_db)):
    stmt = select(Block).order_by(desc(Block.number)).limit(50)
    blocks = db.execute(stmt).scalars().all()
    return templates.TemplateResponse("blocks.html", {"request": request, "blocks": blocks})

@router.get("/txs")
async def list_transactions(request: Request, db: Session = Depends(get_db)):
    stmt = select(Transaction).order_by(desc(Transaction.block_number), desc(Transaction.tx_index)).limit(50)
    txs = db.execute(stmt).scalars().all()
    return templates.TemplateResponse("txs.html", {"request": request, "transactions": txs})

@router.get("/")
async def index(request: Request, db: Session = Depends(get_db)):
    # Fetch latest 10 blocks
    blocks_stmt = select(Block).order_by(desc(Block.number)).limit(10)
    blocks = db.execute(blocks_stmt).scalars().all()
    
    # Fetch latest 10 transactions
    txs_stmt = select(Transaction).order_by(desc(Transaction.block_number), desc(Transaction.tx_index)).limit(10)
    txs = db.execute(txs_stmt).scalars().all()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "blocks": blocks,
        "transactions": txs
    })

@router.get("/block/{block_number}")
async def block_detail(request: Request, block_number: int, db: Session = Depends(get_db)):
    stmt = (
        select(Block)
        .options(selectinload(Block.transactions))
        .where(Block.number == block_number)
    )
    block = db.execute(stmt).scalar_one_or_none()
    
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
        
    return templates.TemplateResponse("block.html", {
        "request": request,
        "block": block
    })

@router.get("/tx/{tx_hash}")
async def transaction_detail(request: Request, tx_hash: str, db: Session = Depends(get_db)):
    query_hash = tx_hash.lower()
    if query_hash.startswith("0x"):
        query_hash = query_hash[2:]
        
    stmt = select(Transaction).where(Transaction.hash == query_hash)
    tx = db.execute(stmt).scalar_one_or_none()
    
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    return templates.TemplateResponse("transaction.html", {
        "request": request,
        "transaction": tx
    })

@router.get("/address/{address}")
async def address_detail(request: Request, address: str, db: Session = Depends(get_db)):
    try:
        checksum_addr = to_checksum_address(address)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid address format")

    stmt = select(Address).where(Address.address == checksum_addr)
    addr_obj = db.execute(stmt).scalar_one_or_none()
    
    if not addr_obj:
        # Check if it has any transactions at least
        stmt_check = select(Transaction).where((Transaction.from_address == checksum_addr) | (Transaction.to_address == checksum_addr)).limit(1)
        has_tx = db.execute(stmt_check).scalar_one_or_none()
        if not has_tx:
             raise HTTPException(status_code=404, detail="Address not found")
        # Create a dummy object if it's not in Address table but has transactions (maybe indexer missed it or it's just a regular account)
        addr_obj = type('obj', (object,), {
            'address': checksum_addr,
            'is_contract': False,
            'balance_cached': 0,
            'first_seen_block': 0
        })

    # Fetch token balances
    tb_stmt = select(TokenBalance).where(TokenBalance.address == checksum_addr)
    balances = db.execute(tb_stmt).scalars().all()
    token_balances = []
    for tb in balances:
        token_info = db.execute(select(Token).where(Token.address == tb.token_address)).scalar_one_or_none()
        token_balances.append({
            "token_address": tb.token_address,
            "symbol": token_info.symbol if token_info else "UNK",
            "decimals": token_info.decimals if token_info else 18,
            "balance": tb.balance
        })

    # Fetch latest transactions for this address
    tx_stmt = select(Transaction).where(
        (Transaction.from_address == checksum_addr) | (Transaction.to_address == checksum_addr)
    ).order_by(desc(Transaction.block_number), desc(Transaction.tx_index)).limit(20)
    txs = db.execute(tx_stmt).scalars().all()

    return templates.TemplateResponse("address.html", {
        "request": request,
        "address": addr_obj,
        "token_balances": token_balances,
        "transactions": txs
    })

@router.get("/api/docs")
async def api_docs(request: Request):
    return templates.TemplateResponse("api_docs.html", {"request": request})

@router.get("/search")
async def search(request: Request, q: str, db: Session = Depends(get_db)):
    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "Search query is empty"})
    
    q = q.strip()
    
    # 1. Check if it's a block number
    if q.isdigit():
        return await block_detail(request, int(q), db)
    
    # 2. Check if it's a Tx Hash (64 chars or 66 with 0x)
    clean_q = q.lower()
    if clean_q.startswith("0x"):
        clean_q = clean_q[2:]
        
    if len(clean_q) == 64:
        # Try finding transaction
        stmt = select(Transaction).where(Transaction.hash == clean_q)
        tx = db.execute(stmt).scalar_one_or_none()
        if tx:
            return await transaction_detail(request, q, db)
        
        # Try finding block by hash
        stmt_b = select(Block).where(Block.hash == clean_q)
        block = db.execute(stmt_b).scalar_one_or_none()
        if block:
            return await block_detail(request, block.number, db)

    # 3. Check if it's an address (40 chars or 42 with 0x)
    if len(clean_q) == 40 or (q.startswith("0x") and len(q) == 42):
        try:
            return await address_detail(request, q, db)
        except HTTPException:
            pass

    return templates.TemplateResponse("index.html", {
        "request": request,
        "error": f"No results found for '{q}'",
        # Need to re-fetch index data or just show error
        "blocks": [],
        "transactions": []
    })
