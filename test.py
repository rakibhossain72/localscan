from web3 import Web3
import random
import time
# ───────────────────────────────────────────────
#  CONFIG – only change these if you really need to
# ───────────────────────────────────────────────

RPC_URL = "http://127.0.0.1:8545"
CHAIN_ID = 31337

# Your token contract address (replace with your deployed ERC-20)
TOKEN_CONTRACT = "0x49A1cc3dDE359E254c48808E4bD83e331A3cC311"          # ← CHANGE THIS

# All private keys (0–9) – using the ones you gave
PRIVATE_KEYS = [
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",   # 0
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",   # 1 – token sender
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",   # 2
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",   # 3
    "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",   # 4
    "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",   # 5
    "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",   # 6
    "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",   # 7
    "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",   # 8
    "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",   # 9
]

TOKEN_PK = PRIVATE_KEYS[1]                  # fixed token sender
ETH_PKS = [PRIVATE_KEYS[0]] + PRIVATE_KEYS[2:]   # 0 + 2–9 for ETH sends

# Amount ranges (you can change these)
ETH_MIN = 0.001
ETH_MAX = 0.02

TOKEN_MIN = 10000000000000      # raw units (not considering decimals)
TOKEN_MAX = 1000000000000000000

# ───────────────────────────────────────────────

w3 = Web3(Web3.HTTPProvider(RPC_URL))

# Minimal ERC-20 transfer ABI
token_abi = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

token_contract = w3.eth.contract(address=TOKEN_CONTRACT, abi=token_abi)

def random_address():
    """Generate a random valid checksummed Ethereum address"""
    pk = "0x" + "".join(random.choice("0123456789abcdef") for _ in range(64))
    acct = w3.eth.account.from_key(pk)
    return acct.address

def send_eth():
    pk = random.choice(ETH_PKS)
    account = w3.eth.account.from_key(pk)
    
    amount_eth = random.uniform(ETH_MIN, ETH_MAX)
    amount_wei = w3.to_wei(2, "ether")
    
    to_addr =  "0xAD16C6F354A438d076A4dF5B1AAb88a1b8eb57E1" #random_address()
    
    nonce = w3.eth.get_transaction_count(account.address, "pending")
    
    tx = {
        "from": account.address,
        "to": to_addr,
        "value": amount_wei,
        "nonce": nonce,
        "gas": 21000,
        "gasPrice": w3.eth.gas_price,
        "chainId": CHAIN_ID,
    }
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    
    print(f"ETH   → {to_addr[:8]}...  amount: {amount_eth:.6f}  from: {account.address[:8]}...  tx: {tx_hash.hex()[:10]}...")

def send_token():
    account = w3.eth.account.from_key(TOKEN_PK)
    
    amount_raw = random.randint(TOKEN_MIN, TOKEN_MAX)
    
    to_addr = random_address()
    
    nonce = w3.eth.get_transaction_count(account.address, "pending")
    
    tx = token_contract.functions.transfer(
        to_addr,
        amount_raw
    ).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 100000,
        "gasPrice": w3.eth.gas_price,
        "chainId": CHAIN_ID,
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    
    print(f"Token → {to_addr[:8]}...  amount: {amount_raw}  from: {account.address[:8]}...  tx: {tx_hash.hex()[:10]}...")

# ───────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting Anvil random sender...\n")
    print(f"Token contract: {TOKEN_CONTRACT}")
    print(f"Token sender:   {w3.eth.account.from_key(TOKEN_PK).address[:8]}...\n")
    
    # You can run this manually each time, or uncomment the loop below
    send_eth()
    send_token()
    
    # If you want it to keep sending forever:
    # while True:
    #     send_eth()
    #     send_token()


