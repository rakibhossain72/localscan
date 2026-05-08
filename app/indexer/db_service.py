from eth_utils import to_checksum_address
from sqlalchemy import delete, select
from app.db.models import Block, Transaction, Address, Contract, Token, TokenTransfer, TokenBalance
from app.indexer.abis import ERC20_ABI

def save_block(session, block_data, w3):
    # We use merge to handle "INSERT OR REPLACE" - upsert semantics
    new_block = Block(
        number=block_data["number"],
        hash=block_data["hash"],
        parent_hash=block_data["parent_hash"],
        timestamp=block_data["timestamp"],
        miner=block_data["miner"],
        gas_used=block_data["gas_used"],
        gas_limit=block_data["gas_limit"],
        tx_count=block_data["tx_count"]
    )
    session.merge(new_block)
    
    # Upsert miner address
    upsert_address(session, w3, to_checksum_address(block_data["miner"]), block_data["number"])


def save_transaction(session, tx, block_number, tx_index, w3):
    receipt = w3.eth.get_transaction_receipt(tx.hash)
    
    new_tx = Transaction(
        hash=tx.hash.hex(),
        block_number=block_number,
        tx_index=tx_index,
        from_address=to_checksum_address(tx["from"]),
        to_address=to_checksum_address(tx["to"]) if tx["to"] else None,
        value=str(tx["value"]),
        gas=tx["gas"],
        gas_price=str(tx["gasPrice"]),
        input=tx["input"].hex(),
        nonce=tx["nonce"],
        status=receipt.status,
        gas_used=receipt.gasUsed,
        custom_error=get_revert_reason(w3, tx.hash.hex()) if receipt.status == 0 else None,
        contract_address=to_checksum_address(tx.get("contractAddress")) if tx.get("contractAddress") else None,
    )
    session.merge(new_tx)

    # ------------------
    # Address & Contract Parsing
    # ------------------
    from_addr = to_checksum_address(tx["from"])
    
    upsert_address(session, w3, from_addr, block_number, is_contract=False)

    to_addr_raw = tx.get("to")
    if to_addr_raw:
        to_addr = to_checksum_address(to_addr_raw)
        upsert_address(session, w3, to_addr, block_number, is_contract=False)
    else:
        # Contract Creation
        contract_address = receipt.get("contractAddress")
        if contract_address:
            c_addr = to_checksum_address(contract_address)
            upsert_address(session, w3, c_addr, block_number, is_contract=True)

            # Save Contract Details
            new_contract = Contract(
                address=c_addr,
                creator_tx=tx.hash.hex(),
                creation_block=block_number,
                bytecode_hash=None
            )
            session.merge(new_contract)
    
    # ------------------
    # ERC20 Log Parsing
    # ------------------
    # Transfer event signature: Transfer(address,address,uint256)
    # topic0 = keccak('Transfer(address,address,uint256)')
    TRANSFER_TOPIC = "ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    
    for log in receipt.logs:
        # Make sure topics is at least length 1 before accessing index 0
        if log.topics and log.topics[0].hex() == TRANSFER_TOPIC and len(log.topics) == 3:
            # It looks like a Transfer event (indexed from, indexed to, uint value)
            token_address = to_checksum_address(log.address)
            
            # Ensure Token exists and is up to date
            ensure_token(session, w3, token_address, force_update=True)
            
            # Extract params
            # topics[1] is from, topics[2] is to. They are 32 bytes, need to strip padding.
            try:
                # eth-utils to_checksum_address handles 42-char str, but topic is 66 chars (0x + 64 hex)
                # We need to take the last 20 bytes (40 hex chars)
                from_hex = "0x" + log.topics[1].hex()[-40:]
                to_hex = "0x" + log.topics[2].hex()[-40:]
                
                t_from = to_checksum_address(from_hex)
                t_to = to_checksum_address(to_hex)
                
                # data contains value
                t_value = int(log.data.hex(), 16)

                
                # Save Token Transfer
                # We should upsert addresses primarily here too in case they were only seen in logs
                upsert_address(session, w3, t_from, block_number)
                upsert_address(session, w3, t_to, block_number)
                
                transfer_rec = TokenTransfer(
                    tx_hash=tx.hash.hex(),
                    block_number=block_number,
                    token_address=token_address,
                    from_address=t_from,
                    to_address=t_to,
                    amount=str(t_value)
                )
                session.add(transfer_rec)
                
                # Update Cached Balances from Chain
                sync_on_chain_token_balance(session, w3, t_from, token_address, block_number)
                sync_on_chain_token_balance(session, w3, t_to, token_address, block_number)
                
            except Exception as e:
                print(f"Error parsing transfer log: {e}")


def ensure_token(session, w3, token_address, force_update=False):
    # Check if token exists, if not, fetch metadata
    token = session.get(Token, token_address)
    if not token or force_update:
        # Fetch from RPC
        try:
            contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
            # Some tokens might fail on these calls (e.g. non-standard ERC20)
            # Use try-except blocks or fallback
            try:
                name = contract.functions.name().call()
            except:
                name = "Unknown"
            
            try:
                symbol = contract.functions.symbol().call()
            except:
                symbol = "UNK"
                
            try:
                decimals = contract.functions.decimals().call()
            except:
                decimals = 18
            
            total_supply_val = None
            try:
                total_supply_val = contract.functions.totalSupply().call()
            except:
                pass
                
            # If we can't get any standard ERC20 info, it's likely not a token
            if name == "Unknown" and symbol == "UNK" and total_supply_val is None:
                return

            new_token = Token(
                address=token_address,
                name=name,
                symbol=symbol,
                decimals=decimals,
                total_supply=str(total_supply_val or 0)
            )
            session.merge(new_token)
            
        except Exception as e:
            # Silently ignore if it's not a contract or doesn't support basic calls
            pass


def upsert_address(session, w3, addr, block_num, is_contract=False):
    # Helper to upsert address and update native balance
    balance = 0
    if w3:
        try:
            balance = w3.eth.get_balance(addr, block_num)
        except Exception as e:
            print(f"Failed to fetch balance for {addr} at block {block_num}: {e}")

    existing = session.get(Address, addr)
    if not existing:
        new_addr = Address(
            address=addr,
            first_seen_block=block_num,
            is_contract=is_contract,
            balance_cached=str(max(0, balance))
        )
        session.add(new_addr)
        # Flush immediately so the identity map is populated — prevents
        # UNIQUE violations when the same address appears multiple times
        # within a single block (e.g. miner appearing in every tx).
        session.flush()
        if is_contract:
            ensure_token(session, w3, addr)
    else:
        existing.balance_cached = str(max(0, balance))
        if is_contract and not existing.is_contract:
            existing.is_contract = True
            ensure_token(session, w3, addr)


def sync_on_chain_token_balance(session, w3, address, token_address, block_num):
    """Fetch exact token balance from chain and sync to DB."""
    try:
        contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        balance = contract.functions.balanceOf(address).call(block_identifier=block_num)
        
        bal_obj = session.get(TokenBalance, {"address": address, "token_address": token_address})
        if bal_obj:
            bal_obj.balance = str(balance)
        else:
            new_obj = TokenBalance(
                address=address,
                token_address=token_address,
                balance=str(balance)
            )
            session.add(new_obj)
        
        # Update holders count
        update_token_holders_count(session, token_address)
    except Exception as e:
        print(f"Error syncing on-chain token balance for {address} on token {token_address}: {e}")

def update_token_balance(session, address, token_address, amount_change):
    # amount_change: positive for addition, negative for subtraction
    bal_obj = session.get(TokenBalance, {"address": address, "token_address": token_address})
    if bal_obj:
        new_bal = int(bal_obj.balance) + amount_change
        bal_obj.balance = str(max(0, new_bal))
    else:
        new_obj = TokenBalance(
            address=address,
            token_address=token_address,
            balance=str(max(0, amount_change))
        )
        session.add(new_obj)
    
    # Update holders count
    update_token_holders_count(session, token_address)


def update_token_holders_count(session, token_address):
    # Count addresses with non-zero balance
    from sqlalchemy import func
    stmt = select(func.count(TokenBalance.address)).where(
        TokenBalance.token_address == token_address,
        TokenBalance.balance != "0"
    )
    count = session.execute(stmt).scalar()
    
    token = session.get(Token, token_address)
    if token:
        token.holders_count = count


def rollback_block(session, block_number):
    # Fetch transfers in this block to reverse balances
    stmt_sel = select(TokenTransfer).where(TokenTransfer.block_number == block_number)
    transfers = session.execute(stmt_sel).scalars().all()
    
    for t in transfers:
        # Reverse the changes: add back to sender, subtract from receiver
        update_token_balance(session, t.from_address, t.token_address, int(t.amount))
        update_token_balance(session, t.to_address, t.token_address, -int(t.amount))

    # Rollback token transfers
    stmt_tt = delete(TokenTransfer).where(TokenTransfer.block_number == block_number)
    session.execute(stmt_tt)

    stmt_tx = delete(Transaction).where(Transaction.block_number == block_number)
    session.execute(stmt_tx)
    
    stmt_block = delete(Block).where(Block.number == block_number)
    session.execute(stmt_block)
    
    session.commit()

def get_revert_reason(w3, tx_hash):
    try:
        tx = w3.eth.get_transaction(tx_hash)
        # We try to call it to get the revert reason
        # Note: Some RPCs might not support this or might require different parameters
        try:
            w3.eth.call({
                "to": tx["to"],
                "from": tx["from"],
                "value": tx["value"],
                "data": tx["input"],
                "gas": tx["gas"],
                "gasPrice": tx["gasPrice"],
            }, tx.blockNumber)
        except Exception as e:
            error_msg = str(e)
            # Clean up common web3 error formats
            if "execution reverted:" in error_msg:
                return error_msg.split("execution reverted:")[-1].strip()
            return error_msg
    except Exception as e:
        print(f"Error fetching revert reason for {tx_hash}: {e}")
    return None
