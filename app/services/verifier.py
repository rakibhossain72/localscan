"""
Contract verification service.
Compiles Solidity source via py-solc-x and compares against on-chain bytecode.
"""

import solcx
import json

from __future__ import annotations
from typing import Optional
from datetime import datetime, timezone
from app.db.models import Contract

def strip_metadata(bytecode: bytes) -> bytes:
    """
    Strip the CBOR-encoded metadata suffix from EVM bytecode.

    Solidity appends a CBOR-encoded metadata blob to the end of deployed
    bytecode.  The last 2 bytes encode the length of that blob (big-endian).
    The full suffix is  <cbor_blob> + <2-byte-length>.

    If the encoded length is inconsistent with the total bytecode length the
    original bytes are returned unchanged.
    """
    if len(bytecode) < 2:
        return bytecode
    metadata_length = int.from_bytes(bytecode[-2:], "big")
    total_suffix = metadata_length + 2
    if total_suffix <= len(bytecode):
        return bytecode[:-total_suffix]
    return bytecode


def compare_bytecodes(a: bytes, b: bytes) -> bool:
    """Return True when both bytecodes are equal after stripping metadata."""
    return strip_metadata(a) == strip_metadata(b)


def compile_contract(
    source: str,
    compiler_version: str,
    optimize: bool,
    runs: int,
) -> dict:
    """
    Compile Solidity source with the given compiler settings.

    Returns {'abi': list, 'bytecode': str, 'error': str | None}.
    """
    try:

        solcx.install_solc(compiler_version)
        compiled = solcx.compile_source(
            source,
            output_values=["abi", "bin"],
            solc_version=compiler_version,
            optimize=optimize,
            optimize_runs=runs,
        )
        # Pick the contract with actual deployable bytecode (skip interfaces/abstract)
        contract_data = None
        for contract_id, data in compiled.items():
            if data.get("bin"):
                contract_data = data
                break

        if contract_data is None:
            return {"abi": None, "bytecode": None, "error": "No deployable contract found in source (all bins are empty)"}

        return {
            "abi": contract_data["abi"],
            "bytecode": contract_data["bin"],
            "error": None,
        }
    except Exception as exc:
        return {"abi": None, "bytecode": None, "error": str(exc)}


def verify_contract(
    db,
    w3,
    address: str,
    source: str,
    compiler_version: str,
    optimize: bool,
    runs: int,
) -> dict:
    """
    Orchestrate: fetch on-chain bytecode → compile → compare → persist.

    Returns {'success': bool, 'message': str}.
    """
    

    contract_row: Optional[Contract] = db.get(Contract, address)
    if contract_row is None:
        return {"success": False, "message": "Contract not found"}

    if contract_row.is_verified:
        return {"success": False, "message": "Contract is already verified"}

    # Fetch on-chain bytecode
    try:
        onchain_bytes: bytes = w3.eth.get_code(address)
    except Exception as exc:
        return {"success": False, "message": f"Could not fetch on-chain bytecode: {exc}"}

    if not onchain_bytes:
        return {"success": False, "message": "On-chain bytecode is empty or unavailable"}

    # Compile
    result = compile_contract(source, compiler_version, optimize, runs)
    if result["error"]:
        return {"success": False, "message": result["error"]}

    compiled_hex: str = result["bytecode"]
    compiled_bytes = bytes.fromhex(compiled_hex.removeprefix("0x"))

    print(len(compiled_bytes), len(onchain_bytes))

    # Compare (metadata-stripped)
    if not compare_bytecodes(compiled_bytes, onchain_bytes):
        return {"success": False, "message": "Bytecode mismatch"}

    contract_row.is_verified = True
    contract_row.source_code = source
    contract_row.abi_json = json.dumps(result["abi"])
    contract_row.compiler_version = compiler_version
    contract_row.optimization_enabled = optimize
    contract_row.optimization_runs = runs
    contract_row.verified_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "message": "Contract verified successfully"}
