from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from typing import Union
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from eth_utils import to_checksum_address
from decimal import Decimal, getcontext

# Set high precision for financial calculations
getcontext().prec = 50

from app.db.models import Block, Transaction, Address, Contract, Token, TokenBalance
from app.dependencies import get_db
from web3 import Web3
from app.indexer.config import RPC_URL
from app.indexer.parser import parse_block
from app.indexer.db_service import save_block, save_transaction, upsert_address
from hexbytes import HexBytes

w3 = Web3(Web3.HTTPProvider(RPC_URL))

router = APIRouter(tags=["views"])
templates = Jinja2Templates(directory="app/templates")

# Register filters
def from_wei_filter(value):
    if value is None: return "0"
    try:
        # Convert to Decimal for exact precision
        human = Decimal(int(value)) / (Decimal(10) ** 18)
        # Format as fixed-point string, normalizing to remove trailing zeros
        return format(human.normalize(), 'f')
    except:
        return value

def format_token_balance(value, decimals=18):
    if value is None: return "0"
    try:
        human = Decimal(int(value)) / (Decimal(10) ** decimals)
        return format(human.normalize(), 'f')
    except:
        return value

def timeago_filter(dt):
    from datetime import datetime, timezone
    if not dt: return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 0: return "just now"
    if seconds < 60: return f"{seconds}s ago"
    if seconds < 3600: return f"{seconds // 60}m ago"
    if seconds < 86400: return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"

templates.env.filters["from_wei"] = from_wei_filter
templates.env.filters["format_token"] = format_token_balance
templates.env.filters["timeago"] = timeago_filter

@router.get("/blocks")
async def list_blocks(request: Request, db: Session = Depends(get_db)):
    stmt = select(Block).order_by(desc(Block.number)).limit(50)
    blocks = db.execute(stmt).scalars().all()
    return templates.TemplateResponse("blocks.html", {"request": request, "blocks": blocks})

@router.get("/txs")
async def list_transactions(request: Request, db: Session = Depends(get_db)):
    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.block))
        .order_by(desc(Transaction.block_number), desc(Transaction.tx_index))
        .limit(50)
    )
    txs = db.execute(stmt).scalars().all()
    return templates.TemplateResponse("txs.html", {"request": request, "transactions": txs})

@router.get("/")
async def index(request: Request, db: Session = Depends(get_db)):
    # Fetch latest 10 blocks
    blocks_stmt = select(Block).order_by(desc(Block.number)).limit(10)
    blocks = db.execute(blocks_stmt).scalars().all()
    
    # Fetch latest 10 transactions
    txs_stmt = (
        select(Transaction)
        .options(selectinload(Transaction.block))
        .order_by(desc(Transaction.block_number), desc(Transaction.tx_index))
        .limit(10)
    )
    txs = db.execute(txs_stmt).scalars().all()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "blocks": blocks,
        "transactions": txs
    })

@router.get("/block/{identifier}")
async def block_detail(request: Request, identifier: Union[int, str], db: Session = Depends(get_db)):
    is_hash = False
    block_number = None
    query_hash = None
    
    if isinstance(identifier, str):
        if identifier.isdigit():
            block_number = int(identifier)
        else:
            is_hash = True
            query_hash = identifier.lower()
            if query_hash.startswith("0x"):
                query_hash = query_hash[2:]
    else:
        block_number = identifier

    if is_hash:
        stmt = (
            select(Block)
            .options(selectinload(Block.transactions))
            .where(Block.hash == query_hash)
        )
    else:
        stmt = (
            select(Block)
            .options(selectinload(Block.transactions))
            .where(Block.number == block_number)
        )
    
    block = db.execute(stmt).scalar_one_or_none()
    
    if not block:
        # Try fetching from chain
        try:
            # parse_block handles both int and hex hash
            data = parse_block(w3, identifier)
            save_block(db, data, w3)
            for i, tx in enumerate(data["transactions"]):
                save_transaction(db, tx, data["number"], i, w3)
            db.commit()
            
            # Re-query after saving
            stmt = (
                select(Block)
                .options(selectinload(Block.transactions))
                .where(Block.number == data["number"])
            )
            block = db.execute(stmt).scalar_one_or_none()
        except Exception as e:
            print(f"Error fetching block {identifier} from chain: {e}")
            raise HTTPException(status_code=404, detail="Block not found")
        
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
        
    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.block))
        .where(Transaction.hash == query_hash)
    )
    tx = db.execute(stmt).scalar_one_or_none()
    
    if not tx:
        # Try fetching from chain
        try:
            full_hash = "0x" + query_hash
            web3_tx = w3.eth.get_transaction(full_hash)
            if web3_tx:
                # Ensure block exists first
                stmt_b = select(Block).where(Block.number == web3_tx.blockNumber)
                block = db.execute(stmt_b).scalar_one_or_none()
                if not block:
                    # Fetch block too
                    block_data = parse_block(w3, web3_tx.blockNumber)
                    save_block(db, block_data, w3)
                    # We could save all txs, but let's at least save this one
                
                # Check if this specific tx is already save by block fetch
                stmt_check = select(Transaction).where(Transaction.hash == query_hash)
                tx = db.execute(stmt_check).scalar_one_or_none()
                if not tx:
                    save_transaction(db, web3_tx, web3_tx.blockNumber, web3_tx.transactionIndex, w3)
                db.commit()
                
                stmt = select(Transaction).where(Transaction.hash == query_hash)
                tx = db.execute(stmt).scalar_one_or_none()
        except Exception as e:
            print(f"Error fetching tx {tx_hash} from chain: {e}")
            raise HTTPException(status_code=404, detail="Transaction not found")

    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    # Fetch associated token transfers
    from app.db.models import TokenTransfer, Token
    tt_stmt = select(TokenTransfer).where(TokenTransfer.tx_hash == query_hash)
    tts = db.execute(tt_stmt).scalars().all()
    
    token_transfers = []
    for tt in tts:
        token_info = db.execute(select(Token).where(Token.address == tt.token_address)).scalar_one_or_none()
        decimals = token_info.decimals if token_info else 18
        human = Decimal(int(tt.amount)) / (Decimal(10) ** decimals)
        token_transfers.append({
            "token_address": tt.token_address,
            "token_name": token_info.name if token_info else "Unknown Token",
            "token_symbol": token_info.symbol if token_info else "UNK",
            "from": tt.from_address,
            "to": tt.to_address,
            "amount": format(human.normalize(), 'f'),
            "decimals": decimals
        })

    return templates.TemplateResponse("transaction.html", {
        "request": request,
        "transaction": tx,
        "token_transfers": token_transfers
    })

@router.get("/address/{address}")
async def address_detail(request: Request, address: str, db: Session = Depends(get_db)):
    try:
        checksum_addr = to_checksum_address(address)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid address format")

    stmt = select(Address).where(Address.address == checksum_addr)
    addr_obj = db.execute(stmt).scalar_one_or_none()
    
    # Check if this address is a Token contract
    stmt_token = select(Token).where(Token.address == checksum_addr)
    token_exists = db.execute(stmt_token).scalar_one_or_none()
    if token_exists:
        return RedirectResponse(url=f"/token/{checksum_addr}")

    if not addr_obj:
        # Try fetching from chain
        try:
            code = w3.eth.get_code(checksum_addr)
            is_contract = len(code) > 0
            upsert_address(db, w3, checksum_addr, w3.eth.block_number, is_contract=is_contract)
            db.commit()
            
            stmt = select(Address).where(Address.address == checksum_addr)
            addr_obj = db.execute(stmt).scalar_one_or_none()
        except Exception as e:
            print(f"Error fetching address {checksum_addr} from chain: {e}")

    if not addr_obj:
        # Check if it has any transactions at least (fallback for partially indexed)
        stmt_check = select(Transaction).where((Transaction.from_address == checksum_addr) | (Transaction.to_address == checksum_addr)).limit(1)
        has_tx = db.execute(stmt_check).scalar_one_or_none()
        if not has_tx:
             raise HTTPException(status_code=404, detail="Address not found")
        # Create a dummy object
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
        decimals = token_info.decimals if token_info else 18
        raw_balance = int(tb.balance)
        human = Decimal(raw_balance) / (Decimal(10) ** decimals)
        formatted_balance = format(human.normalize(), 'f')
        token_balances.append({
            "token_address": tb.token_address,
            "symbol": token_info.symbol if token_info else "UNK",
            "decimals": decimals,
            "balance": tb.balance,
            "formatted_balance": formatted_balance
        })

    # Fetch latest transactions for this address
    tx_stmt = select(Transaction).where(
        (Transaction.from_address == checksum_addr) | (Transaction.to_address == checksum_addr)
    ).order_by(desc(Transaction.block_number), desc(Transaction.tx_index)).limit(20)
    txs = db.execute(tx_stmt).scalars().all()

    # Fetch latest token transfers for this address
    from app.db.models import TokenTransfer
    tt_stmt = select(TokenTransfer).where(
        (TokenTransfer.from_address == checksum_addr) | (TokenTransfer.to_address == checksum_addr)
    ).order_by(desc(TokenTransfer.block_number), desc(TokenTransfer.id)).limit(20)
    tts = db.execute(tt_stmt).scalars().all()
    
    token_txs = []
    for tt in tts:
        token_info = db.execute(select(Token).where(Token.address == tt.token_address)).scalar_one_or_none()
        decimals = token_info.decimals if token_info else 18
        human = Decimal(int(tt.amount)) / (Decimal(10) ** decimals)
        token_txs.append({
            "tx_hash": tt.tx_hash,
            "block_number": tt.block_number,
            "token_address": tt.token_address,
            "token_symbol": token_info.symbol if token_info else "UNK",
            "from": tt.from_address,
            "to": tt.to_address,
            "amount": format(human.normalize(), 'f')
        })

    return templates.TemplateResponse("address.html", {
        "request": request,
        "address": addr_obj,
        "token_balances": token_balances,
        "transactions": txs,
        "token_transfers": token_txs
    })

@router.get("/token/{address}")
async def token_detail(request: Request, address: str, db: Session = Depends(get_db)):
    try:
        checksum_addr = to_checksum_address(address)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid address format")

    stmt = select(Token).where(Token.address == checksum_addr)
    token = db.execute(stmt).scalar_one_or_none()
    
    if not token:
        # If it's not a token, maybe it's just a regular address
        return await address_detail(request, address, db)

    # Fetch top holders - need to sort by numeric balance
    from sqlalchemy import cast, Numeric
    holders_stmt = (
        select(TokenBalance)
        .where(TokenBalance.token_address == checksum_addr)
        .order_by(desc(cast(TokenBalance.balance, Numeric)))
        .limit(5)
    )
    holders_objs = db.execute(holders_stmt).scalars().all()
    
    # Fetch token transfers for history
    from app.db.models import TokenTransfer
    transfers_stmt = (
        select(TokenTransfer)
        .where(TokenTransfer.token_address == checksum_addr)
        .order_by(desc(TokenTransfer.block_number), desc(TokenTransfer.id))
        .limit(20)
    )
    transfers = db.execute(transfers_stmt).scalars().all()

    # Format holders
    formatted_holders = []
    for h in holders_objs:
        raw_bal = int(h.balance)
        human = Decimal(raw_bal) / (Decimal(10) ** token.decimals) if token.decimals else Decimal(raw_bal)
        formatted_holders.append({
            "address": h.address,
            "balance": h.balance,
            "formatted_balance": format(human.normalize(), 'f')
        })

    # Format transfers
    formatted_transfers = []
    for t in transfers:
        raw_amt = int(t.amount)
        human = Decimal(raw_amt) / (Decimal(10) ** token.decimals) if token.decimals else Decimal(raw_amt)
        formatted_transfers.append({
            "tx_hash": t.tx_hash,
            "from_address": t.from_address,
            "to_address": t.to_address,
            "amount": t.amount,
            "formatted_amount": format(human.normalize(), 'f')
        })

    return templates.TemplateResponse("token.html", {
        "request": request,
        "token": token,
        "holders": formatted_holders,
        "transfers": formatted_transfers
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
    
    # 2. Check if it's an address (40 chars or 42 with 0x)
    clean_q = q.lower()
    address_q = clean_q
    if address_q.startswith("0x"):
        address_q = address_q[2:]
        
    if len(address_q) == 40:
        try:
            return await address_detail(request, q, db)
        except HTTPException:
            pass

    # 3. Check if it's a Tx Hash or Block Hash (64 chars or 66 with 0x)
    hash_q = clean_q
    if hash_q.startswith("0x"):
        hash_q = hash_q[2:]
        
    if len(hash_q) == 64:
        # Try finding transaction first
        try:
            return await transaction_detail(request, q, db)
        except HTTPException:
            # If not a transaction, maybe it's a block hash
            try:
                # We need to find block number by hash first if we want to use block_detail(int)
                # Or modify block_detail to handle hash strings too.
                # Let's try block_detail with the hash string directly
                return await block_detail(request, q, db)
            except HTTPException:
                pass

    return templates.TemplateResponse("index.html", {
        "request": request,
        "error": f"No results found for '{q}'",
        "blocks": [],
        "transactions": []
    })
