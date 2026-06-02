#!/usr/bin/env python3
"""Initialize twscrape for nave X fetch (``nave stocks x-analyze``, registry)."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DB = PROJECT_ROOT / "var" / "x_accounts.db"


def _load_dotenv() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path)


def _db_path() -> Path:
    raw = os.getenv("X_ACCOUNTS_DB")
    return Path(raw) if raw else DEFAULT_DB


async def _add_from_env(pool: Any) -> bool:
    """Add one account from env if credentials are present."""
    username = os.getenv("X_SCRAPE_USERNAME", "").strip()
    password = os.getenv("X_SCRAPE_PASSWORD", "").strip()
    email = os.getenv("X_SCRAPE_EMAIL", "").strip()
    email_password = os.getenv("X_SCRAPE_EMAIL_PASSWORD", "").strip()
    cookies = os.getenv("X_SCRAPE_COOKIES", "").strip()

    if cookies:
        if not username:
            print("X_SCRAPE_COOKIES set but X_SCRAPE_USERNAME is required", file=sys.stderr)
            return False
        await pool.add_account(
            username=username,
            password=password or "unused",
            email=email or f"{username}@local",
            email_password=email_password or "unused",
            cookies=cookies,
        )
        return True

    if not all([username, password, email, email_password]):
        return False

    await pool.add_account(
        username=username,
        password=password,
        email=email,
        email_password=email_password,
    )
    return True


async def _run_setup(*, login: bool) -> int:
    from twscrape import AccountsPool

    db = _db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    pool = AccountsPool(str(db))

    added = await _add_from_env(pool)
    if added:
        print(f"Account added to {db}")
    elif not db.is_file():
        print(
            "No credentials in env. Set one of:\n"
            "  • X_SCRAPE_USERNAME + X_SCRAPE_PASSWORD + X_SCRAPE_EMAIL + X_SCRAPE_EMAIL_PASSWORD\n"
            "  • X_SCRAPE_USERNAME + X_SCRAPE_COOKIES (JSON: ct0 + auth_token from browser)\n"
            "Or: twscrape --db var/x_accounts.db add_accounts accounts.txt "
            "username:password:email:email_password",
            file=sys.stderr,
        )
        return 1

    if login:
        print("Logging in accounts (may take a minute)...")
        stats = await pool.login_all()
        print(stats)

    return 0


async def _run_check() -> int:
    db = _db_path()
    if not db.is_file():
        print(f"[MISSING] {db}")
        print("Run: python3 scripts/setup_x_twscrape.py --setup")
        return 1

    from twscrape import AccountsPool

    pool = AccountsPool(str(db))
    accounts = await pool.accounts_info()
    active = sum(1 for a in accounts if a.get("active"))
    logged = sum(1 for a in accounts if a.get("logged_in"))
    print(f"[OK] {db} — accounts={len(accounts)} active={active} logged_in={logged}")
    for row in accounts:
        print(
            f"  @{row['username']}: active={row['active']} "
            f"logged_in={row['logged_in']} err={row.get('error_msg') or '-'}"
        )
    if active == 0:
        print("No active accounts — run: python3 scripts/setup_x_twscrape.py --setup --login")
        return 1
    return 0


async def _run_probe(ticker: str, limit: int) -> int:
    for k in ("X_BEARER_TOKEN", "TWITTER_BEARER_TOKEN"):
        os.environ.pop(k, None)

    from trading.stocks.x_client import XClient, XClientError

    client = XClient(accounts_db=_db_path())
    try:
        posts = await client.fetch_recent_posts(ticker, days=7, limit=limit)
    except XClientError as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        return 1

    print(f"Fetched {len(posts)} posts for {ticker}")
    for p in posts[:5]:
        print(f"  @{p.username} | {p.created_at[:10]} | {p.text[:100]}")
    return 0 if posts else 1


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Show account DB status")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Add account from env and optionally login",
    )
    parser.add_argument("--login", action="store_true", help="With --setup, run login_all")
    parser.add_argument(
        "--probe",
        metavar="TICKER",
        help="Test fetch via twscrape (ignores Bearer token)",
    )
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    if args.check:
        return asyncio.run(_run_check())
    if args.setup:
        return asyncio.run(_run_setup(login=args.login))
    if args.probe:
        if asyncio.run(_run_check()) != 0:
            return 1
        return asyncio.run(_run_probe(args.probe.upper(), args.limit))

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())