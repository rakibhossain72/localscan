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

@settings(max_examples=100)
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
