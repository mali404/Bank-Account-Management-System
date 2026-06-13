"""Seed the database with demo users (one per role) and a couple of accounts.

Run via: `python -m scripts.seed_demo`
"""
from __future__ import annotations

import asyncio
import secrets as _secrets
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

from app.security.auth import hash_password
from app.security.rbac import Role

DEMO_USERS = [
    ("alice@example.com",   Role.CUSTOMER,           "Alice Customer",   "CNIC-AAAA-0001"),
    ("bob@example.com",     Role.CUSTOMER,           "Bob Customer",     "CNIC-AAAA-0002"),
    ("teller@example.com",  Role.TELLER,             "Tina Teller",      "EMP-T-0001"),
    ("loan@example.com",    Role.LOAN_OFFICER,       "Larry Loan",       "EMP-L-0001"),
    ("comp@example.com",    Role.COMPLIANCE_OFFICER, "Casey Compliance", "EMP-C-0001"),
    ("admin@example.com",   Role.ADMIN,              "Adam Admin",       "EMP-A-0001"),
]


DEFAULT_PASSWORD = "ChangeMe-DemoPw#2025"



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
        # Resolve the column DEK from the env-provided file path; passed
        # as a SQL parameter to pgcrypto.
        from app.core.settings import get_settings

        dek = get_settings().db_column_dek_path.read_bytes().hex()

        for email, role, name, gov_id in DEMO_USERS:
            uid = uuid4()
            await session.execute(
                text(
                    "INSERT INTO users (id,email,password_hash,role,is_active) "
                    "VALUES (:id,:email,:pwh,:role,TRUE) ON CONFLICT (email) DO NOTHING"
                ),
                {"id": uid, "email": email, "pwh": hash_password(DEFAULT_PASSWORD), "role": role.value},
            )

            if role == Role.CUSTOMER:
                # Look up the user_id we may have just inserted (or pre-existing).
                row = await session.execute(
                    text("SELECT id FROM users WHERE email=:e"), {"e": email}
                )
                user_id = row.scalar_one()

                await session.execute(
                    text(
                        """
                        INSERT INTO customers (id, user_id, full_name, gov_id, dob)
                        VALUES (
                            :cid, :uid,
                            pgp_sym_encrypt(:fn, :dek),
                            pgp_sym_encrypt(:gid, :dek),
                            pgp_sym_encrypt(:dob, :dek)
                        )
                        ON CONFLICT (user_id) DO NOTHING
                        """
                    ),
                    {"cid": uuid4(), "uid": user_id, "fn": name, "gid": gov_id, "dob": "1990-01-01", "dek": dek},
                )

                # Open a checking account with $10,000 demo balance.
                customer_id = (
                    await session.execute(
                        text("SELECT id FROM customers WHERE user_id=:u"), {"u": user_id}
                    )
                ).scalar_one()
                await session.execute(
                    text(
                        """
                        INSERT INTO accounts (id, customer_id, account_number, account_type, balance)
                        VALUES (:id, :cid, :num, 'checking', :bal)
                        ON CONFLICT (account_number) DO NOTHING
                        """
                    ),
                    {
                        "id": uuid4(),
                        "cid": customer_id,
                        "num": str(_secrets.randbelow(10**12)).zfill(12),
                        "bal": Decimal("10000.00"),
                    },
                )

    print("Seeded demo users with default password:", DEFAULT_PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())
