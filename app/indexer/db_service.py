from eth_utils import to_checksum_address
from sqlalchemy import delete, select
from app.db.models import Block, Transaction, Address, Contract, Token, TokenTransfer
from app.indexer.abis import ERC20_ABI

def save_block(session, block_data):
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


def save_transaction(session, tx, block_number, tx_index, w3):
    receipt = w3.eth.get_transaction_receipt(tx.hash)
    
    new_tx = Transaction(
        hash=tx.hash.hex(),
        block_number=block_number,
        tx_index=tx_index,
        from_address=to_checksum_address(tx["from"]),
        to_address=to_checksum_address(tx["to"]) if tx["to"] else None,
        value=tx["value"],
        gas=tx["gas"],
        gas_price=tx["gasPrice"],
        input=tx["input"].hex(),
        nonce=tx["nonce"],
        status=receipt.status
    )
    session.merge(new_tx)

    # ------------------
    # Address & Contract Parsing
    # ------------------
    from_addr = to_checksum_address(tx["from"])
    
    upsert_address(session, from_addr, block_number, is_contract=False)

    to_addr_raw = tx.get("to")
    if to_addr_raw:
        to_addr = to_checksum_address(to_addr_raw)
        upsert_address(session, to_addr, block_number, is_contract=False)
    else:
        # Contract Creation
        contract_address = receipt.get("contractAddress")
        if contract_address:
            c_addr = to_checksum_address(contract_address)
            upsert_address(session, c_addr, block_number, is_contract=True)

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
    TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    
    for log in receipt.logs:
        # Make sure topics is at least length 1 before accessing index 0
        if log.topics and log.topics[0].hex() == TRANSFER_TOPIC and len(log.topics) == 3:
            # It looks like a Transfer event (indexed from, indexed to, uint value)
            token_address = to_checksum_address(log.address)
            
            # Ensure Token exists
            ensure_token(session, w3, token_address)
            
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
                upsert_address(session, t_from, block_number)
                upsert_address(session, t_to, block_number)
                
                transfer_rec = TokenTransfer(
                    tx_hash=tx.hash.hex(),
                    block_number=block_number,
                    token_address=token_address,
                    from_address=t_from,
                    to_address=t_to,
                    amount=t_value
                )
                session.add(transfer_rec)
                
            except Exception as e:
                print(f"Error parsing transfer log: {e}")


def ensure_token(session, w3, token_address):
    # Check if token exists, if not, fetch metadata
    token = session.get(Token, token_address)
    if not token:
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
            
            try:
                total_supply = contract.functions.totalSupply().call()
            except:
                total_supply = 0
                
            new_token = Token(
                address=token_address,
                name=name,
                symbol=symbol,
                decimals=decimals,
                total_supply=total_supply
            )
            session.add(new_token)
            
            # Also ensure it's in contracts/addresses
            # We assume it is a contract 
            upsert_address(session, token_address, 0, is_contract=True)
            
        except Exception as e:
            print(f"Failed to fetch token info for {token_address}: {e}")


def upsert_address(session, addr, block_num, is_contract=False):
    # Helper to upsert address
    # We use session.get or check existing to update flags if needed
    existing = session.get(Address, addr)
    if not existing:
        new_addr = Address(
            address=addr,
            first_seen_block=block_num,
            is_contract=is_contract,
            balance_cached=0 
        )
        session.add(new_addr)
    else:
        # Update contract flag if we just discovered it's a contract
        if is_contract and not existing.is_contract:
            existing.is_contract = True


def rollback_block(session, block_number):
    # Rollback token transfers
    stmt_tt = delete(TokenTransfer).where(TokenTransfer.block_number == block_number)
    session.execute(stmt_tt)

    stmt_tx = delete(Transaction).where(Transaction.block_number == block_number)
    session.execute(stmt_tx)
    
    stmt_block = delete(Block).where(Block.number == block_number)
    session.execute(stmt_block)
    
    session.commit()
