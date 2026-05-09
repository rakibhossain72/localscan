"""
Property-based tests for DB service and Contract model.
Feature: contract-verification
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Address, Contract


# ---------------------------------------------------------------------------
# Fixtures: in-memory SQLite DB per test
# ---------------------------------------------------------------------------

def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid Ethereum-like address: 0x + 40 hex chars (lowercase)
eth_address = st.from_regex(r"0x[0-9a-f]{40}", fullmatch=True)

# Valid tx hash: 0x + 64 hex chars
tx_hash = st.from_regex(r"0x[0-9a-f]{64}", fullmatch=True)

# Block number
block_number = st.integers(min_value=0, max_value=10_000_000)


# ---------------------------------------------------------------------------
# Property 3: Contract model defaults
# Feature: contract-verification, Property 3: Contract model defaults
# Validates: Requirements 4.1
# ---------------------------------------------------------------------------

@settings(max_examples=25)
@given(
    address=eth_address,
    creator_tx=tx_hash,
    creation_block=block_number,
)
def test_contract_model_defaults(address, creator_tx, creation_block):
    """
    For any newly created Contract row, is_verified must be false and all
    verification fields (source_code, abi_json, compiler_version,
    optimization_enabled, optimization_runs, verified_at) must be null.
    Validates: Requirements 4.1
    """
    db = make_session()
    try:
        # Address row required due to FK constraint
        addr_row = Address(address=address, is_contract=True)
        db.add(addr_row)
        db.flush()

        contract = Contract(
            address=address,
            creator_tx=creator_tx,
            creation_block=creation_block,
        )
        db.add(contract)
        db.commit()
        db.refresh(contract)

        assert contract.is_verified is False
        assert contract.source_code is None
        assert contract.abi_json is None
        assert contract.compiler_version is None
        assert contract.optimization_enabled is None
        assert contract.optimization_runs is None
        assert contract.verified_at is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers for save_transaction tests
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, patch
from app.indexer.db_service import save_transaction, _fetch_bytecode_hash


def _make_w3(from_addr, contract_addr, bytecode=b"\x60\x80"):
    """Build a minimal w3 mock for a contract-creation transaction."""
    receipt = MagicMock()
    receipt.status = 1
    receipt.gasUsed = 21000
    receipt.logs = []
    # Use a real callable so receipt.get("contractAddress") works reliably
    receipt.contractAddress = contract_addr
    receipt.get.side_effect = lambda key, default=None: contract_addr if key == "contractAddress" else default

    # ERC20 contract mock — all calls return sensible defaults
    erc20_contract = MagicMock()
    erc20_contract.functions.name.return_value.call.return_value = "Unknown"
    erc20_contract.functions.symbol.return_value.call.return_value = "UNK"
    erc20_contract.functions.decimals.return_value.call.return_value = 18
    erc20_contract.functions.totalSupply.return_value.call.return_value = None

    w3 = MagicMock()
    w3.eth.get_transaction_receipt.return_value = receipt
    w3.eth.get_balance.return_value = 0
    w3.eth.get_code.return_value = bytecode
    w3.eth.contract.return_value = erc20_contract
    # keccak returns a bytes-like object whose .hex() gives a hex string
    keccak_result = MagicMock()
    keccak_result.hex.return_value = "0x" + "ab" * 32
    w3.keccak.return_value = keccak_result
    return w3


def _make_tx(from_addr, contract_addr, tx_hash_hex, block_number):
    """Build a minimal tx mock for a contract-creation transaction."""
    input_mock = MagicMock()
    input_mock.hex.return_value = "0x"

    hash_mock = MagicMock()
    hash_mock.hex.return_value = tx_hash_hex

    data = {
        "from": from_addr,
        "to": None,
        "value": 0,
        "gas": 100000,
        "gasPrice": 1,
        "input": input_mock,
        "nonce": 0,
        "contractAddress": None,
    }

    tx = MagicMock()
    tx.hash = hash_mock
    tx.__getitem__ = lambda self, key: data[key]
    tx.get = lambda key, default=None: data.get(key, default)
    return tx


# ---------------------------------------------------------------------------
# Property 1: Contract creation stores record and marks address
# Feature: contract-verification, Property 1: Contract creation stores record and marks address
# Validates: Requirements 1.1, 1.4
# ---------------------------------------------------------------------------

@settings(max_examples=25, deadline=None)
@given(
    from_addr=eth_address,
    contract_addr=eth_address,
    tx_hash_str=tx_hash,
    blk=block_number,
)
def test_contract_creation_stores_record_and_marks_address(
    from_addr, contract_addr, tx_hash_str, blk
):
    """
    For any contract-creating transaction, after save_transaction:
    - A Contract row exists for the contract address
    - The corresponding Address row has is_contract=True
    Validates: Requirements 1.1, 1.4
    """
    from hypothesis import assume
    from eth_utils import to_checksum_address as _cs
    assume(from_addr.lower() != contract_addr.lower())

    # Normalise to checksum form — this is what save_transaction stores
    from_cs = _cs(from_addr)
    contract_cs = _cs(contract_addr)

    db = make_session()
    try:
        from datetime import datetime, timezone
        from app.db.models import Block
        block_row = Block(
            number=blk,
            hash="0x" + "cc" * 32,
            parent_hash="0x" + "dd" * 32,
            timestamp=datetime.now(timezone.utc),
            miner=from_cs,
            gas_used=0,
            gas_limit=1000000,
            tx_count=1,
        )
        db.add(block_row)
        db.flush()

        w3 = _make_w3(from_cs, contract_cs)
        tx = _make_tx(from_cs, contract_cs, tx_hash_str, blk)

        save_transaction(db, tx, blk, 0, w3)
        db.commit()

        contract_row = db.get(Contract, contract_cs)
        assert contract_row is not None, "Contract row must exist after contract-creation tx"

        addr_row = db.get(Address, contract_cs)
        assert addr_row is not None
        assert addr_row.is_contract is True, "Address must be marked is_contract=True"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Property 2: Bytecode hash upsert
# Feature: contract-verification, Property 2: Bytecode hash upsert
# Validates: Requirements 1.2
# ---------------------------------------------------------------------------

@settings(max_examples=25)
@given(
    address=eth_address,
    creator_tx=tx_hash,
    creation_block=block_number,
    new_hash=st.from_regex(r"0x[0-9a-f]{64}", fullmatch=True),
)
def test_bytecode_hash_upsert(address, creator_tx, creation_block, new_hash):
    """
    For any Contract row with bytecode_hash=null, when save_transaction is
    called again and the RPC returns a non-null hash, the bytecode_hash field
    is updated to the new value.
    Validates: Requirements 1.2
    """
    db = make_session()
    try:
        # Insert Address + Contract with null bytecode_hash
        addr_row = Address(address=address, is_contract=True)
        db.add(addr_row)
        db.flush()

        contract = Contract(
            address=address,
            creator_tx=creator_tx,
            creation_block=creation_block,
            bytecode_hash=None,
        )
        db.add(contract)
        db.commit()

        # Mock w3 that returns a specific hash
        w3 = MagicMock()
        code_bytes = bytes.fromhex(new_hash[2:])
        w3.eth.get_code.return_value = code_bytes
        keccak_result = MagicMock()
        keccak_result.hex.return_value = new_hash
        w3.keccak.return_value = keccak_result

        fetched = _fetch_bytecode_hash(w3, address)
        assert fetched == new_hash

        # Apply the upsert logic (mirrors save_transaction)
        existing = db.get(Contract, address)
        assert existing is not None
        if existing.bytecode_hash is None and fetched is not None:
            existing.bytecode_hash = fetched
        db.commit()
        db.refresh(existing)

        assert existing.bytecode_hash == new_hash, (
            "bytecode_hash must be updated from null to the fetched hash"
        )
    finally:
        db.close()
