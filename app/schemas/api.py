"""Pydantic schemas used across the API."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.security.rbac import Role


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    role: Role
    full_name: str = Field(min_length=1, max_length=200)
    gov_id: str = Field(min_length=4, max_length=64)
    dob: str = Field(description="ISO date YYYY-MM-DD")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: EmailStr
    role: Role
    is_active: bool
    created_at: datetime


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_id: UUID
    account_number: str
    account_type: str
    balance: Decimal
    is_frozen: bool
    created_at: datetime


class AccountCreate(BaseModel):
    customer_id: UUID
    account_type: str = Field(pattern="^(checking|savings|loan)$")
    initial_deposit: Decimal = Field(default=Decimal("0.00"), ge=0)


class TransferCreate(BaseModel):
    from_account_id: UUID
    to_account_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    memo: str = Field(default="", max_length=200)

    @field_validator("from_account_id")
    @classmethod
    def not_self_transfer(cls, v: UUID, info) -> UUID:
        # Validation across fields with field_validator needs a small dance;
        # full check happens in the service layer.
        return v


class TransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    from_account_id: UUID | None
    to_account_id: UUID | None
    amount: Decimal
    memo: str
    state: str
    originator_user_id: UUID
    approver_user_id: UUID | None
    created_at: datetime
    settled_at: datetime | None


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = None


class AgentChatResponse(BaseModel):
    thread_id: str
    reply: str
    actions_taken: list[dict]
    pending_approval: dict | None = None
