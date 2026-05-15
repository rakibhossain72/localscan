# LocalScan

A lightweight EVM blockchain indexer and explorer. LocalScan connects to any EVM-compatible node via WebSocket, indexes blocks and transactions in real time into a local SQLite database, and exposes a web UI alongside a REST API for querying chain data.

## Features

- Real-time block and transaction indexing via WebSocket (`eth_subscribe`)
- ERC-20 transfer log tracking and token balance caching
- Address, contract, and token metadata resolution
- Web-based block explorer UI
- REST API for blocks, transactions, and addresses
- SQLite storage — no external database required
- Automatic reconnect and reorg detection

## Requirements

- Python 3.10 or higher
- An EVM-compatible node with WebSocket and HTTP RPC endpoints (e.g. Anvil, Hardhat, Geth, Reth)

## Installation

### From PyPI (pip)

```bash
pip install localscan
```

### From Source

```bash
git clone https://github.com/your-org/localscan.git
cd localscan
git submodule update --init --recursive
pip install .
```

### Development Install

```bash
git clone https://github.com/your-org/localscan.git
cd localscan
git submodule update --init --recursive
pip install -e .
```

## Usage

### Start the Explorer

```bash
localscan
```

This starts the indexer and web server on `http://127.0.0.1:8000` by default, connecting to a local node at `ws://127.0.0.1:8545`.

### Options

```
localscan [OPTIONS]

  --host          Bind host (default: 127.0.0.1)
  --port          Bind port (default: 8000)
  --rpc-url       WebSocket RPC URL (default: ws://127.0.0.1:8545)
  --http-rpc-url  HTTP RPC URL for receipts and calls (default: http://127.0.0.1:8545)
  --db            Path to the SQLite database file (default: chain_indexer.db)
  --keep-db       Keep the existing database on startup instead of wiping it
  --reload        Enable auto-reload for development
```

### Example — Connect to a Custom Node

```bash
localscan \
  --rpc-url ws://my-node:8546 \
  --http-rpc-url http://my-node:8545 \
  --port 3000 \
  --keep-db
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
    indexer/      # Block ingestion, chain-sniper integration
    db/           # SQLAlchemy models and session
    routes/       # FastAPI route handlers
    templates/    # Jinja2 HTML templates
    static/       # CSS and JS assets
    cli.py        # Entry point
    main.py       # FastAPI application
  chain-sniper/   # WebSocket block subscription submodule
  alembic/        # Database migrations
```

## Database Migrations

LocalScan uses Alembic for schema migrations.

```bash
alembic upgrade head
```

## License

MIT — see [LICENSE](LICENSE).
