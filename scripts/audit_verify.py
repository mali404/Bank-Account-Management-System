"""Walk the audit_events chain and verify every HMAC.

Run with the *admin* DB user — the runtime app role doesn't need this.
Returns exit code 0 on clean chain, 1 on any tamper detection.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.settings import get_settings
from app.observability.audit import verify_chain


async def main() -> int:
    s = get_settings()
    # Use the asyncpg URL but with admin credentials.
    admin_url = s.database_admin_url.replace("+psycopg", "+asyncpg")
    engine = create_async_engine(admin_url)
    sm = async_sessionmaker(engine)

    async with sm() as session:
        ok, bad_id = await verify_chain(session)

    if ok:
        print("audit chain: OK")
        return 0
    print(f"audit chain: TAMPERED at id={bad_id}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
