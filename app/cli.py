import argparse
import os
import pathlib
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="LocalScan — EVM blockchain explorer")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    parser.add_argument(
        "--rpc-url",
        default="ws://127.0.0.1:8545",
        help="RPC URL — ws/wss for WebSocket subscription, http/https for polling (default: ws://127.0.0.1:8545)",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the existing database across runs (default: delete on startup)",
    )
    parser.add_argument(
        "--db",
        default="chain_indexer.db",
        help="Path to the SQLite database file (default: chain_indexer.db)",
    )
    args = parser.parse_args()

    # Patch config before the app modules are imported by uvicorn
    import app.indexer.config as cfg
    cfg.RPC_URL = args.rpc_url
    cfg.DB_PATH = args.db

    db_path = pathlib.Path(args.db)
    if not args.keep_db and db_path.exists():
        print(f"[localscan] Removing existing database: {db_path}")
        os.remove(db_path)

    # Re-initialise the engine now that DB_PATH is set
    import app.db.session as db_session
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_session.engine = create_engine(
        f"sqlite:///{cfg.DB_PATH}",
        connect_args={"check_same_thread": False},
    )
    db_session.SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.engine
    )

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
