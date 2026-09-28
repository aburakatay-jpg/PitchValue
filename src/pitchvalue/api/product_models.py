"""Public-safe product-service request and response contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class UserResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    user_id: str
    account_kind: str
    email: str | None
    email_verified: bool


class SessionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime


class EmailRegistrationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    session: SessionResponse
    delivery_state: str


class EmailAuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)


class EmailRegistrationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)
    country_code: str = Field(min_length=2, max_length=2)
    age_18_acknowledged: bool


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=512)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    new_password: str = Field(min_length=8, max_length=1024)


class EmailVerificationResendResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    delivery_state: str


class EmailVerificationConfirmRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)


class ExternalAuthRequest(BaseModel):
    provider_token: str = Field(min_length=20, max_length=8192)


class CommerceVerificationRequestModel(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    external_transaction_id: str = Field(min_length=1, max_length=500)
    product_identifier: str = Field(min_length=1, max_length=500)
    plan: str
    verification_token: str = Field(min_length=1, max_length=65536)


class CommerceCatalogResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    state: str
    plans: tuple[str, ...]
    prices: tuple[str, ...]
    trial_eligibility: str


class EntitlementResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    state: str
    source: str
    product_identifier: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    trial: bool


class SaveSelectionRequest(BaseModel):
    match_id: int = Field(gt=0)
    market: str = Field(min_length=1, max_length=100)
    selection: str = Field(min_length=1, max_length=100)
    line: Decimal | None = None
    saved_decimal_odds: Decimal | None = Field(default=None, gt=1)
    stake: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class SavedSelectionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    saved_selection_id: str
    match_id: int
    market: str
    selection: str
    line: Decimal | None
    saved_decimal_odds: Decimal | None
    stake: Decimal | None
    currency: str | None
    tracking_status: str
    outcome: str | None
    created_at: datetime


class SavedSelectionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    records: tuple[SavedSelectionResponse, ...]
    count: int


class PerformanceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    tracked: int
    wins: int
    losses: int
    voids: int
    withdrawn: int
    total_stake: Decimal | None
    net_return: Decimal | None
    roi: Decimal | None


class ExplainRequest(BaseModel):
    match_id: int = Field(gt=0)
    market: str = Field(min_length=1, max_length=100)
    selection: str = Field(min_length=1, max_length=100)
    question: str | None = Field(default=None, max_length=1000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    match_id: int | None = Field(default=None, gt=0)
    market: str | None = Field(default=None, max_length=100)
    selection: str | None = Field(default=None, max_length=100)


class PublicContextResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    match_id: int
    market: str
    selection: str
    publication_state: str
    model_probability: Decimal
    bet_score: Decimal | None
    edge: Decimal | None
    final_check: str
    limitations: tuple[str, ...]


class AssistantResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    state: str
    answer: str | None
    context: PublicContextResponse | None


class CouponRequest(BaseModel):
    risk: str
    requested_count: int = Field(ge=1, le=4)


class CouponResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    state: str
    risk: str
    requested_count: int
    selections: tuple[PublicContextResponse, ...]


class ServiceReadinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    AUTH_READY: str
    ENTITLEMENT_READY: str
    COMMERCE_ACTIVATION_READY: str
    MY_BETS_READY: str
    AI_CONTRACT_READY: str
    COUPON_BUILDER_READY: str


class ProviderCredential(BaseModel):
    credential_type: str = Field(min_length=1, max_length=100)
    credential_value: str = Field(min_length=1, max_length=8192)


class AccountDeletionRequest(BaseModel):
    password_or_token: str | None = Field(default=None, max_length=8192)
    provider_credential: ProviderCredential | None = None


class AccountDeletionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    deletion_state: str
    has_active_store_subscription: bool = False
    subscription_provider: str | None = None
