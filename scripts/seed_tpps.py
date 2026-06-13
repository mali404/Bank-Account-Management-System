"""Register two demo TPPs: one AISP, one PISP.

Run via: python -m scripts.seed_tpps

Default credentials (do NOT use outside the demo):
  AcmeAggregator (AISP):  client_id=acme-aisp     client_secret=acme-secret-001
  ZippyPay (PISP):        client_id=zippy-pisp    client_secret=zippy-secret-001
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import text

from app.security.auth import hash_password


TPPS = [
    {
        "id": uuid4(),
        "client_id": "acme-aisp",
        "secret": "acme-secret-001",
        "organisation_name": "Acme Aggregator Ltd.",
        "software_id": "acme-app-prod",
        "roles": ["AISP"],
        "redirect_uris": ["https://acme.example.com/callback"],
    },
    {
        "id": uuid4(),
        "client_id": "zippy-pisp",
        "secret": "zippy-secret-001",
        "organisation_name": "ZippyPay Payments Ltd.",
        "software_id": "zippy-app-prod",
        "roles": ["PISP"],
        "redirect_uris": ["https://zippypay.example.com/callback"],
    },
]



def _admin_sessionmaker():
    """Seeds run as the DB admin: FORCE RLS blocks the runtime app role
    from inserting rows on behalf of identities that aren't in session
    context. The postgres superuser bypasses RLS by design."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.settings import get_settings

    url = get_settings().database_admin_url.replace("+psycopg", "+asyncpg")
    return async_sessionmaker(create_async_engine(url), expire_on_commit=False)


async def main() -> None:
    sm = _admin_sessionmaker()
    async with sm() as session, session.begin():
        for t in TPPS:
            await session.execute(
                text(
                    """
                    INSERT INTO third_party_providers
                      (id, client_id, client_secret_hash, organisation_name,
                       software_id, roles, redirect_uris, is_active)
                    VALUES
                      (:id, :cid, :hsh, :org, :sw,
                       CAST(:roles AS varchar[]), CAST(:uris AS varchar[]), TRUE)
                    ON CONFLICT (client_id) DO NOTHING
                    """
                ),
                {
                    "id": t["id"],
                    "cid": t["client_id"],
                    "hsh": hash_password(t["secret"]),
                    "org": t["organisation_name"],
                    "sw": t["software_id"],
                    "roles": "{" + ",".join(t["roles"]) + "}",
                    "uris": "{" + ",".join(t["redirect_uris"]) + "}",
                },
            )

    print("Seeded TPPs:")
    for t in TPPS:
        print(f"  {t['client_id']:14s}  secret={t['secret']}  roles={t['roles']}")


if __name__ == "__main__":
    asyncio.run(main())
