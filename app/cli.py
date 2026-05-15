import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="LocalScan — EVM blockchain explorer")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    parser.add_argument(
        "--rpc-url",
        default="ws://127.0.0.1:8545",
        help="WebSocket RPC URL for block subscription (default: ws://127.0.0.1:8545)",
    )
    parser.add_argument(
        "--http-rpc-url",
        default="http://127.0.0.1:8545",
        help="HTTP RPC URL for receipts/calls (default: http://127.0.0.1:8545)",
    )
    args = parser.parse_args()

    # Patch config before the app modules are imported by uvicorn
    import app.indexer.config as cfg
    cfg.RPC_URL = args.rpc_url
    cfg.HTTP_RPC_URL = args.http_rpc_url

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
