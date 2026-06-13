"""OBIE Read/Write API v4.0 wire schemas.

These are deliberately verbose to match OBIE field naming conventions
(PascalCase in JSON, with OB-prefixed type names). Internal models stay
snake_case; mapping happens at the router boundary.

OBIE-GAP: Field-by-field exhaustiveness is not implemented — we cover
the fields a real AISP/PISP would consume in v4.0, not every namespaced
enumeration. Comments mark divergences from spec.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


def _new_meta_id() -> str:
    return str(uuid4())


# --- Common envelope ----------------------------------------------------


class OBLinks(BaseModel):
    """Links section of an OBIE response."""

    Self: str
    First: str | None = None
    Prev: str | None = None
    Next: str | None = None
    Last: str | None = None


class OBMeta(BaseModel):
    TotalPages: int = 1
    FirstAvailableDateTime: datetime | None = None
    LastAvailableDateTime: datetime | None = None


class OBResponse(BaseModel, Generic[T]):
    """Standard OBIE response envelope: Data + Risk + Links + Meta.

    OBIE-GAP: `Risk` is empty by default for AISP responses (per spec).
    For PISP we populate it.
    """

    model_config = ConfigDict(populate_by_name=True)

    Data: T
    Risk: dict = Field(default_factory=dict)
    Links: OBLinks
    Meta: OBMeta = Field(default_factory=OBMeta)


# --- Account / Balance / Transaction (AISP) -----------------------------


class OBAccountIdentifier(BaseModel):
    """OBIE namespaced account identifier.

    For UK domestic this is typically `UK.OBIE.SortCodeAccountNumber`. We
    model it generically so non-UK ids work too (PSU is in Pakistan in
    the demo seed data).
    """

    SchemeName: str  # e.g. "UK.OBIE.SortCodeAccountNumber"
    Identification: str
    Name: str | None = None
    SecondaryIdentification: str | None = None


class OBAmount(BaseModel):
    Amount: Decimal
    Currency: str = "GBP"  # default per spec; overridable


class OBAccount(BaseModel):
    """OBReadAccount6/Data/Account."""

    AccountId: str
    Status: Literal["Enabled", "Disabled", "Deleted", "ProForma", "Pending"] = "Enabled"
    StatusUpdateDateTime: datetime
    Currency: str
    AccountType: Literal["Business", "Personal"] = "Personal"
    AccountSubType: Literal[
        "ChargeCard", "CreditCard", "CurrentAccount", "EMoney",
        "Loan", "Mortgage", "PrePaidCard", "Savings",
    ]
    Nickname: str | None = None
    OpeningDate: datetime | None = None
    Account: list[OBAccountIdentifier]


class OBAccountListData(BaseModel):
    Account: list[OBAccount]


class OBBalance(BaseModel):
    """OBReadBalance1/Data/Balance."""

    AccountId: str
    Amount: OBAmount
    CreditDebitIndicator: Literal["Credit", "Debit"]
    Type: Literal[
        "ClosingAvailable", "ClosingBooked", "ClosingCleared",
        "Expected", "ForwardAvailable", "Information", "InterimAvailable",
        "InterimBooked", "InterimCleared", "OpeningAvailable",
        "OpeningBooked", "OpeningCleared", "PreviouslyClosedBooked",
    ] = "InterimBooked"
    DateTime: datetime


class OBBalanceListData(BaseModel):
    Balance: list[OBBalance]


class OBTransaction(BaseModel):
    """OBReadTransaction6/Data/Transaction (subset)."""

    AccountId: str
    TransactionId: str
    Status: Literal["Booked", "Pending"] = "Booked"
    BookingDateTime: datetime
    ValueDateTime: datetime | None = None
    TransactionInformation: str | None = None
    Amount: OBAmount
    CreditDebitIndicator: Literal["Credit", "Debit"]


class OBTransactionListData(BaseModel):
    Transaction: list[OBTransaction]


# --- AISP consent -------------------------------------------------------

OBPermission = Literal[
    "ReadAccountsBasic",
    "ReadAccountsDetail",
    "ReadBalances",
    "ReadTransactionsBasic",
    "ReadTransactionsDetail",
    "ReadTransactionsCredits",
    "ReadTransactionsDebits",
]


class OBAccountAccessConsentRequestData(BaseModel):
    Permissions: list[OBPermission]
    ExpirationDateTime: datetime | None = None
    TransactionFromDateTime: datetime | None = None
    TransactionToDateTime: datetime | None = None


class OBAccountAccessConsentRequest(BaseModel):
    Data: OBAccountAccessConsentRequestData
    Risk: dict = Field(default_factory=dict)


class OBAccountAccessConsentResponseData(BaseModel):
    ConsentId: str
    CreationDateTime: datetime
    Status: Literal["AwaitingAuthorisation", "Authorised", "Rejected", "Revoked"] = "AwaitingAuthorisation"
    StatusUpdateDateTime: datetime
    Permissions: list[OBPermission]
    ExpirationDateTime: datetime | None = None
    TransactionFromDateTime: datetime | None = None
    TransactionToDateTime: datetime | None = None


# --- PISP: domestic payment consent ------------------------------------


class OBRemittanceInformation(BaseModel):
    Unstructured: str | None = None
    Reference: str | None = None


class OBInitiation(BaseModel):
    """Subset of OBDomesticInitiation."""

    InstructionIdentification: str = Field(default_factory=_new_meta_id)
    EndToEndIdentification: str = Field(default_factory=_new_meta_id)
    InstructedAmount: OBAmount
    DebtorAccount: OBAccountIdentifier | None = None  # optional in spec
    CreditorAccount: OBAccountIdentifier
    RemittanceInformation: OBRemittanceInformation | None = None


class OBRiskBlock(BaseModel):
    """OBIE Risk block. Required for PISP. We model the
    most-frequently-checked fields; the rest are accepted but ignored."""

    PaymentContextCode: Literal[
        "BillPayment", "EcommerceGoods", "EcommerceServices",
        "PartyToParty", "Other",
    ] | None = None
    MerchantCategoryCode: str | None = None
    MerchantCustomerIdentification: str | None = None


class OBDomesticPaymentConsentRequestData(BaseModel):
    Initiation: OBInitiation


class OBDomesticPaymentConsentRequest(BaseModel):
    Data: OBDomesticPaymentConsentRequestData
    Risk: OBRiskBlock = Field(default_factory=OBRiskBlock)


class OBDomesticPaymentConsentResponseData(BaseModel):
    ConsentId: str
    CreationDateTime: datetime
    Status: Literal[
        "AwaitingAuthorisation", "Authorised", "Consumed", "Rejected",
    ] = "AwaitingAuthorisation"
    StatusUpdateDateTime: datetime
    Initiation: OBInitiation


class OBDomesticPaymentRequestData(BaseModel):
    ConsentId: str
    Initiation: OBInitiation


class OBDomesticPaymentRequest(BaseModel):
    Data: OBDomesticPaymentRequestData
    Risk: OBRiskBlock = Field(default_factory=OBRiskBlock)


class OBDomesticPaymentResponseData(BaseModel):
    DomesticPaymentId: str
    ConsentId: str
    CreationDateTime: datetime
    Status: Literal[
        "Pending", "Rejected", "AcceptedSettlementInProcess",
        "AcceptedSettlementCompleted", "AcceptedWithoutPosting", "AcceptedCreditSettlementCompleted",
    ] = "Pending"
    StatusUpdateDateTime: datetime
    Initiation: OBInitiation


# --- Open Data ---------------------------------------------------------


class OpenDataBranch(BaseModel):
    """Trimmed OB Open Data branch shape — enough for a portfolio demo."""

    Identification: str
    Name: str
    Address: dict
    LocationCategory: list[str] = Field(default_factory=lambda: ["Branch"])


class OpenDataATM(BaseModel):
    Identification: str
    SupportedCurrencies: list[str] = Field(default_factory=lambda: ["GBP"])
    Address: dict
    Access24HoursIndicator: bool = False


class OpenDataPCA(BaseModel):
    """Personal current account product. Heavily trimmed."""

    Name: str
    Identification: str
    BrandName: str = "Agentic Bank"
    OverdraftEligible: bool = True


# --- OBIE error envelope ------------------------------------------------


class OBErrorItem(BaseModel):
    ErrorCode: str  # e.g. "UK.OBIE.Resource.NotAuthorised"
    Message: str
    Path: str | None = None
    Url: str | None = None


class OBError(BaseModel):
    Code: str
    Id: str = Field(default_factory=_new_meta_id)
    Message: str
    Errors: list[OBErrorItem] = Field(default_factory=list)
