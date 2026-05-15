# LocalScan

A lightweight EVM blockchain indexer and explorer. LocalScan connects to any EVM-compatible node via WebSocket or HTTP, indexes blocks and transactions in real time into a local SQLite database, and exposes a web UI alongside a REST API for querying chain data.

## Features

- Real-time block indexing via WebSocket (`eth_subscribe`) or HTTP polling — use whatever your node supports
- ERC-20 transfer log tracking and token balance caching
- Address, contract, and token metadata resolution
- Web-based block explorer UI
- REST API for blocks, transactions, and addresses
- SQLite storage — no external database required
- Automatic reconnect and reorg detection

## Requirements

- Python 3.10 or higher
- An EVM-compatible node with an RPC endpoint (e.g. Anvil, Hardhat, Geth, Reth, Infura, Alchemy)

## Installation

```bash
pip install localscan
```

### From Source

```bash
git clone https://github.com/rakibhossain72/localscan.git
cd localscan
pip install -e .
```

## Usage

```bash
localscan --rpc-url <RPC_URL>
```

LocalScan auto-detects the protocol from the URL:

- `ws://` or `wss://` → WebSocket mode using `eth_subscribe` (real-time, recommended)
- `http://` or `https://` → HTTP polling mode (polls for new blocks every 2 seconds)

### Examples

```bash
# Local Anvil / Hardhat node — WebSocket
localscan --rpc-url ws://localhost:8545

# Local node — HTTP polling
localscan --rpc-url http://localhost:8545

# Remote node — WebSocket
localscan --rpc-url wss://mainnet.infura.io/ws/v3/YOUR_KEY

# Remote node — HTTPS polling
localscan --rpc-url https://mainnet.infura.io/v3/YOUR_KEY

# Custom port, persistent database
localscan --rpc-url ws://localhost:8545 --port 3000 --keep-db
```

### All Options

```
  --rpc-url    RPC endpoint — ws/wss for WebSocket, http/https for polling
               (default: ws://127.0.0.1:8545)
  --host       Bind host (default: 127.0.0.1)
  --port       Bind port (default: 8000)
  --db         Path to SQLite database file (default: chain_indexer.db)
  --keep-db    Keep existing database on startup instead of wiping it
  --reload     Enable auto-reload for development
```

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/blocks/{block_number}` | Get block by number |
| GET | `/transactions/{tx_hash}` | Get transaction by hash |
| GET | `/addresses/{address}` | Get address, contract, and token info |

All endpoints return JSON. The web UI is served at `/`.

## Project Structure

```
localscan/
  app/
    indexer/    # Block ingestion, WebSocket and HTTP polling modes
    db/         # SQLAlchemy models and session
    routes/     # FastAPI route handlers
    templates/  # Jinja2 HTML templates
    static/     # CSS assets
    cli.py      # Entry point
    main.py     # FastAPI application
  alembic/      # Database migrations
```

## License

MIT — see [LICENSE](LICENSE).
