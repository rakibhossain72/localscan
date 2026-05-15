"""Database write operations for indexed chain data."""
from sqlalchemy import delete, func, select

from eth_utils import to_checksum_address

from app.db.models import (
    Address,
    Block,
    Contract,
    Token,
    TokenBalance,
    TokenTransfer,
    Transaction,
)
from app.indexer.abis import ERC20_ABI

TRANSFER_TOPIC = "ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _fetch_bytecode_hash(w3, address: str):
    """Fetch deployed bytecode and return keccak256 hex hash, or None on failure."""
    try:
        code = w3.eth.get_code(address)
        if code:
            return w3.keccak(code).hex()
    except Exception:  # noqa: BLE001
        pass
    return None


def save_block(session, block_data, w3):
    """Upsert a block row and its miner address."""
    new_block = Block(
        number=block_data["number"],
        hash=block_data["hash"],
        parent_hash=block_data["parent_hash"],
        timestamp=block_data["timestamp"],
        miner=block_data["miner"],
        gas_used=block_data["gas_used"],
        gas_limit=block_data["gas_limit"],
        tx_count=block_data["tx_count"],
    )
    session.merge(new_block)
    upsert_address(session, w3, to_checksum_address(block_data["miner"]), block_data["number"])


def save_transaction(session, tx, block_number, tx_index, w3):
    """Upsert a transaction and all derived data (addresses, contracts, token transfers)."""
    receipt = w3.eth.get_transaction_receipt(tx.hash)

    receipt_contract_address = receipt.get("contractAddress")
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
        contract_address=(
            to_checksum_address(receipt_contract_address) if receipt_contract_address else None
        ),
    )
    session.merge(new_tx)

    from_addr = to_checksum_address(tx["from"])
    upsert_address(session, w3, from_addr, block_number, is_contract=False)

    to_addr_raw = tx.get("to")
    if to_addr_raw:
        upsert_address(
            session, w3, to_checksum_address(to_addr_raw), block_number, is_contract=False
        )
    else:
        contract_address = receipt.get("contractAddress")
        if contract_address:
            c_addr = to_checksum_address(contract_address)
            upsert_address(session, w3, c_addr, block_number, is_contract=True)
            bytecode_hash = _fetch_bytecode_hash(w3, c_addr)
            existing_contract = session.get(Contract, c_addr)
            if existing_contract:
                if existing_contract.bytecode_hash is None and bytecode_hash is not None:
                    existing_contract.bytecode_hash = bytecode_hash
            else:
                session.merge(Contract(
                    address=c_addr,
                    creator_tx=tx.hash.hex(),
                    creation_block=block_number,
                    bytecode_hash=bytecode_hash,
                ))

    _process_transfer_logs(session, w3, receipt.logs, tx.hash.hex(), block_number)


def _process_transfer_logs(session, w3, logs, tx_hash, block_number):
    """Parse ERC-20 Transfer logs from a transaction receipt."""
    for log in logs:
        if not (log.topics and log.topics[0].hex() == TRANSFER_TOPIC and len(log.topics) == 3):
            continue

        token_address = to_checksum_address(log.address)
        ensure_token(session, w3, token_address, force_update=True)

        try:
            from_hex = "0x" + log.topics[1].hex()[-40:]
            to_hex = "0x" + log.topics[2].hex()[-40:]
            t_from = to_checksum_address(from_hex)
            t_to = to_checksum_address(to_hex)
            t_value = int(log.data.hex(), 16)

            upsert_address(session, w3, t_from, block_number)
            upsert_address(session, w3, t_to, block_number)

            session.add(TokenTransfer(
                tx_hash=tx_hash,
                block_number=block_number,
                token_address=token_address,
                from_address=t_from,
                to_address=t_to,
                amount=str(t_value),
            ))

            sync_on_chain_token_balance(session, w3, t_from, token_address, block_number)
            sync_on_chain_token_balance(session, w3, t_to, token_address, block_number)
        except Exception as exc:  # noqa: BLE001
            print(f"Error parsing transfer log: {exc}")


def ensure_token(session, w3, token_address, force_update=False):
    """Fetch ERC-20 metadata from chain and upsert into the tokens table."""
    token = session.get(Token, token_address)
    if token and not force_update:
        return

    try:
        contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        try:
            name = contract.functions.name().call()
        except Exception:  # noqa: BLE001
            name = "Unknown"

        try:
            symbol = contract.functions.symbol().call()
        except Exception:  # noqa: BLE001
            symbol = "UNK"

        try:
            decimals = contract.functions.decimals().call()
        except Exception:  # noqa: BLE001
            decimals = 18

        total_supply_val = None
        try:
            total_supply_val = contract.functions.totalSupply().call()
        except Exception:  # noqa: BLE001
            pass

        if name == "Unknown" and symbol == "UNK" and total_supply_val is None:
            return

        if token:
            token.name = name
            token.symbol = symbol
            token.decimals = decimals
            token.total_supply = str(total_supply_val or 0)
        else:
            session.add(Token(
                address=token_address,
                name=name,
                symbol=symbol,
                decimals=decimals,
                total_supply=str(total_supply_val or 0),
            ))
            session.flush()

    except Exception:  # noqa: BLE001
        pass


def upsert_address(session, w3, addr, block_num, is_contract=False):
    """Upsert an address row and refresh its native balance."""
    balance = 0
    if w3:
        try:
            balance = w3.eth.get_balance(addr, block_num)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to fetch balance for {addr} at block {block_num}: {exc}")

    existing = session.get(Address, addr)
    if not existing:
        session.add(Address(
            address=addr,
            first_seen_block=block_num,
            is_contract=is_contract,
            balance_cached=str(max(0, balance)),
        ))
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
            session.add(TokenBalance(
                address=address,
                token_address=token_address,
                balance=str(balance),
            ))

        update_token_holders_count(session, token_address)
    except Exception as exc:  # noqa: BLE001
        print(f"Error syncing on-chain token balance for {address} on token {token_address}: {exc}")


def update_token_balance(session, address, token_address, amount_change):
    """Adjust a cached token balance by amount_change (positive = add, negative = subtract)."""
    bal_obj = session.get(TokenBalance, {"address": address, "token_address": token_address})
    if bal_obj:
        new_bal = int(bal_obj.balance) + amount_change
        bal_obj.balance = str(max(0, new_bal))
    else:
        session.add(TokenBalance(
            address=address,
            token_address=token_address,
            balance=str(max(0, amount_change)),
        ))
    update_token_holders_count(session, token_address)


def update_token_holders_count(session, token_address):
    """Recount and update the holders_count field on the token row."""
    stmt = select(func.count(TokenBalance.address)).where(  # pylint: disable=not-callable
        TokenBalance.token_address == token_address,
        TokenBalance.balance != "0",
    )
    count = session.execute(stmt).scalar()
    token = session.get(Token, token_address)
    if token:
        token.holders_count = count


def rollback_block(session, block_number):
    """Remove a block and all its derived data (used during reorg handling)."""
    stmt_sel = select(TokenTransfer).where(TokenTransfer.block_number == block_number)
    transfers = session.execute(stmt_sel).scalars().all()

    for t in transfers:
        update_token_balance(session, t.from_address, t.token_address, int(t.amount))
        update_token_balance(session, t.to_address, t.token_address, -int(t.amount))

    session.execute(delete(TokenTransfer).where(TokenTransfer.block_number == block_number))
    session.execute(delete(Transaction).where(Transaction.block_number == block_number))
    session.execute(delete(Block).where(Block.number == block_number))
    session.commit()


def get_revert_reason(w3, tx_hash):
    """Attempt to retrieve the revert reason for a failed transaction."""
    try:
        tx = w3.eth.get_transaction(tx_hash)
        try:
            w3.eth.call({
                "to": tx["to"],
                "from": tx["from"],
                "value": tx["value"],
                "data": tx["input"],
                "gas": tx["gas"],
                "gasPrice": tx["gasPrice"],
            }, tx.blockNumber)
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            if "execution reverted:" in error_msg:
                return error_msg.rsplit("execution reverted:", maxsplit=1)[-1].strip()
            return error_msg
    except Exception as exc:  # noqa: BLE001
        print(f"Error fetching revert reason for {tx_hash}: {exc}")
    return None
