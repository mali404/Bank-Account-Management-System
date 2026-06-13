"""Open Data API (OBIE) — no auth required.

Returns realistic-shaped catalogue data. Static for the demo; in a real
ASPSP this would come from a CMS. Kept tiny and synthetic on purpose.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.openbanking.schemas.obie import (
    OBLinks,
    OBMeta,
    OBResponse,
    OpenDataATM,
    OpenDataBranch,
    OpenDataPCA,
)

router = APIRouter(prefix="/open-banking/v4.0", tags=["open-banking:open-data"])


@router.get("/branches")
def list_branches(request: Request) -> OBResponse[dict]:
    branches = [
        OpenDataBranch(
            Identification="BR-001",
            Name="Agentic Bank — Chicago Loop",
            Address={"StreetName": "10 South Wacker Dr", "TownName": "Chicago", "Country": "US"},
        ),
        OpenDataBranch(
            Identification="BR-002",
            Name="Agentic Bank — London Bridge",
            Address={"StreetName": "1 London Bridge", "TownName": "London", "Country": "GB"},
        ),
    ]
    return OBResponse(
        Data={"Brand": [{"BrandName": "Agentic Bank", "Branch": [b.model_dump() for b in branches]}]},
        Links=OBLinks(Self=str(request.url)),
        Meta=OBMeta(LastAvailableDateTime=datetime.now(UTC)),
    )


@router.get("/atms")
def list_atms(request: Request) -> OBResponse[dict]:
    atms = [
        OpenDataATM(
            Identification="ATM-001",
            Address={"StreetName": "10 South Wacker Dr", "TownName": "Chicago", "Country": "US"},
            Access24HoursIndicator=True,
        )
    ]
    return OBResponse(
        Data={"Brand": [{"BrandName": "Agentic Bank", "ATM": [a.model_dump() for a in atms]}]},
        Links=OBLinks(Self=str(request.url)),
        Meta=OBMeta(LastAvailableDateTime=datetime.now(UTC)),
    )


@router.get("/personal-current-accounts")
def list_pcas(request: Request) -> OBResponse[dict]:
    products = [
        OpenDataPCA(
            Name="Everyday Checking",
            Identification="PCA-001",
            BrandName="Agentic Bank",
            OverdraftEligible=True,
        ),
        OpenDataPCA(
            Name="Student Checking",
            Identification="PCA-002",
            BrandName="Agentic Bank",
            OverdraftEligible=False,
        ),
    ]
    return OBResponse(
        Data={"PersonalCurrentAccount": [p.model_dump() for p in products]},
        Links=OBLinks(Self=str(request.url)),
        Meta=OBMeta(LastAvailableDateTime=datetime.now(UTC)),
    )
