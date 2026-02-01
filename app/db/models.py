from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ChainState(Base):
    __tablename__ = "chain_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[int] = mapped_column(nullable=False, unique=True)
    last_block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_block_hash: Mapped[str] = mapped_column(
        String(66), nullable=False
    )  # 0x + 64 chars
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("chain_id > 0", name="ck_chain_id_positive"),
        CheckConstraint("last_block_number >= 0", name="ck_last_block_non_negative"),
    )


class Block(Base):
    __tablename__ = "blocks"

    number: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    hash: Mapped[str] = mapped_column(String(66), unique=True, nullable=False)
    parent_hash: Mapped[str] = mapped_column(String(66), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    miner: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    gas_used: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gas_limit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_count: Mapped[int] = mapped_column(Integer, nullable=False)

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="block", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    hash: Mapped[str] = mapped_column(String(66), primary_key=True)
    block_number: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("blocks.number", ondelete="CASCADE"), nullable=False
    )
    tx_index: Mapped[int] = mapped_column(Integer, nullable=False)
    from_address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    to_address: Mapped[Optional[str]] = mapped_column(
        String(42), nullable=True, index=True
    )
    value: Mapped[str] = mapped_column(String(78), nullable=False)  # wei as string (max ~2^256)
    gas: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gas_price: Mapped[str] = mapped_column(String(78), nullable=False)  # wei as string
    input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    nonce: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # 0 = fail, 1 = success, None = pending/old
    contract_address: Mapped[Optional[str]] = mapped_column(
        String(42), nullable=True, index=True
    )

    block: Mapped["Block"] = relationship(back_populates="transactions")

    __table_args__ = (
        Index("ix_transactions_block_number_tx_index", "block_number", "tx_index"),
        CheckConstraint("nonce >= 0", name="ck_nonce_non_negative"),
    )


class Address(Base):
    __tablename__ = "addresses"

    address: Mapped[str] = mapped_column(String(42), primary_key=True)
    first_seen_block: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    is_contract: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    balance_cached: Mapped[Optional[str]] = mapped_column(
        String(78), nullable=True
    )  # wei as string

    __table_args__ = (
        CheckConstraint(
            "balance_cached IS NULL OR (SUBSTR(balance_cached, 1, 1) <> '-')",
            name="ck_address_balance_non_negative"
        ),
    )


class Contract(Base):
    __tablename__ = "contracts"

    address: Mapped[str] = mapped_column(
        String(42),
        ForeignKey("addresses.address", ondelete="CASCADE"),
        primary_key=True,
    )
    creator_tx: Mapped[str] = mapped_column(String(66), nullable=False)
    creation_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bytecode_hash: Mapped[str] = mapped_column(
        String(66), nullable=True
    )  # keccak256 of runtime bytecode

    # Optional fields you can add later
    # verified_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # abi_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Token(Base):
    __tablename__ = "tokens"

    address: Mapped[str] = mapped_column(
        String(42),
        ForeignKey("contracts.address", ondelete="CASCADE"),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=True)
    decimals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_supply: Mapped[Optional[str]] = mapped_column(String(78), nullable=True)  # as string

    __table_args__ = (
        CheckConstraint(
            "total_supply IS NULL OR (SUBSTR(total_supply, 1, 1) <> '-')",
            name="ck_token_total_supply_non_negative"
        ),
    )


class TokenTransfer(Base):
    __tablename__ = "token_transfers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tx_hash: Mapped[str] = mapped_column(
        String(66),
        ForeignKey("transactions.hash", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    token_address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    from_address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    to_address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    amount: Mapped[str] = mapped_column(
        String(78), nullable=False
    )  # raw amount as string (no decimals applied)

    __table_args__ = (
        Index("ix_token_transfers_token_from", "token_address", "from_address"),
        Index("ix_token_transfers_token_to", "token_address", "to_address"),
    )


class TokenBalance(Base):
    __tablename__ = "token_balances"

    address: Mapped[str] = mapped_column(String(42), primary_key=True)
    token_address: Mapped[str] = mapped_column(String(42), primary_key=True)
    balance: Mapped[str] = mapped_column(String(78), nullable=False, default="0")

    __table_args__ = (
        Index("ix_token_balances_address", "address"),
        Index("ix_token_balances_token_address", "token_address"),
        CheckConstraint(
            "SUBSTR(balance, 1, 1) <> '-'",
            name="ck_token_balance_non_negative"
        ),
    )
