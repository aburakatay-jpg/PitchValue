"""Authenticated, user-scoped product service routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import Connection

from pitchvalue.api.dependencies import (
    get_auth_limiter,
    get_bearer_token,
    get_connection,
    get_current_user,
    get_transaction,
    get_verified_user,
)
from pitchvalue.api.errors import ApiError, ErrorCode
from pitchvalue.api.product_models import (
    AccountDeletionRequest,
    AccountDeletionResponse,
    AskRequest,
    AssistantResponse,
    CommerceCatalogResponse,
    CommerceVerificationRequestModel,
    CouponRequest,
    CouponResponse,
    EmailAuthRequest,
    EmailRegistrationRequest,
    EmailRegistrationResponse,
    EmailVerificationConfirmRequest,
    EmailVerificationResendResponse,
    EntitlementResponse,
    ExplainRequest,
    ExternalAuthRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PerformanceResponse,
    PublicContextResponse,
    RefreshRequest,
    SavedSelectionListResponse,
    SavedSelectionResponse,
    SaveSelectionRequest,
    ServiceReadinessResponse,
    SessionResponse,
    UserResponse,
)
from pitchvalue.operations.release_validation import validate_product_service_readiness
from pitchvalue.prediction.repository import current_predictions, published_predictions
from pitchvalue.product_services.abuse import AuthAction, AuthRateLimited, InMemoryAuthLimiter
from pitchvalue.product_services.assistant import (
    CouponResult,
    CouponRisk,
    CouponState,
    ExternalAssistantAdapter,
    build_coupon,
    explain_public_prediction,
    public_context,
    unsupported_prediction_request,
)
from pitchvalue.product_services.auth import (
    AuthError,
    IssuedSession,
    ProductUser,
    UnconfiguredAppleIdentityVerifier,
    UnconfiguredGoogleIdentityVerifier,
    UnconfiguredPasswordResetDelivery,
    authenticate_external,
    confirm_email_verification,
    confirm_password_reset,
    create_guest_session,
    login_email,
    logout,
    normalize_email,
    refresh_session,
    register_email,
    request_password_reset,
    resend_email_verification,
)
from pitchvalue.product_services.entitlements import (
    CommerceVerificationRequest,
    EntitlementState,
    ExternalCommerceVerifier,
    resolve_entitlement,
)
from pitchvalue.product_services.tracking import (
    SavedSelection,
    TrackingError,
    get_saved_selection,
    list_saved_selections,
    performance,
    remove_saved_selection,
    save_public_selection,
)

router = APIRouter(tags=["product-services"])


@router.post("/auth/guest", response_model=SessionResponse)
def guest_session(
    connection: Annotated[Connection, Depends(get_transaction)],
) -> SessionResponse:
    return _session(create_guest_session(connection))


@router.post("/auth/email/register", response_model=EmailRegistrationResponse)
def email_register(
    request: EmailRegistrationRequest,
    http_request: Request,
    limiter: Annotated[InMemoryAuthLimiter, Depends(get_auth_limiter)],
    connection: Annotated[Connection, Depends(get_transaction)],
) -> EmailRegistrationResponse:
    _guard_auth(limiter, AuthAction.REGISTER, _client(http_request))
    if not request.age_18_acknowledged:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, "18+ acknowledgement is required")
    try:
        session, delivery_state = register_email(
            connection, request.email, request.password, request.country_code
        )
        return EmailRegistrationResponse(
            session=_session(session),
            delivery_state=delivery_state,
        )
    except AuthError as error:
        raise ApiError(409, ErrorCode.CONFLICT, str(error)) from error


@router.post("/auth/email/login", response_model=SessionResponse)
def email_login(
    request: EmailAuthRequest,
    http_request: Request,
    limiter: Annotated[InMemoryAuthLimiter, Depends(get_auth_limiter)],
    connection: Annotated[Connection, Depends(get_transaction)],
) -> SessionResponse:
    client = _client(http_request)
    principal = request.email.strip().casefold()
    _guard_auth(limiter, AuthAction.LOGIN, client, principal)
    try:
        session = _session(login_email(connection, request.email, request.password))
        limiter.reset(AuthAction.LOGIN, client, principal)
        return session
    except AuthError as error:
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "Invalid credentials") from error


@router.post("/auth/email/password-reset", status_code=202)
def email_password_reset(
    request: PasswordResetRequest,
    connection: Annotated[Connection, Depends(get_transaction)],
) -> Response:
    try:
        raw_token = request_password_reset(connection, request.email)
        if raw_token:
            normalized = normalize_email(request.email)
            UnconfiguredPasswordResetDelivery().request_reset(normalized, raw_token)
    except AuthError as error:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, "Invalid email") from error
    except RuntimeError as error:
        raise ApiError(
            503,
            ErrorCode.EXTERNAL_ACTIVATION_REQUIRED,
            "Password reset delivery requires external activation",
        ) from error
    return Response(status_code=202)


@router.post("/auth/email/password-reset/confirm", status_code=204)
def email_password_reset_confirm(
    request: PasswordResetConfirmRequest,
    connection: Annotated[Connection, Depends(get_transaction)],
) -> Response:
    try:
        confirm_password_reset(connection, request.token, request.new_password)
    except AuthError as error:
        if "password does not meet" in str(error):
            raise ApiError(422, ErrorCode.VALIDATION_ERROR, str(error)) from error
        raise ApiError(400, ErrorCode.VALIDATION_ERROR, str(error)) from error
    return Response(status_code=204)


@router.post("/auth/email/verification/confirm", status_code=204)
def email_verification_confirm(
    request: EmailVerificationConfirmRequest,
    connection: Annotated[Connection, Depends(get_transaction)],
) -> Response:
    try:
        confirm_email_verification(connection, request.token)
    except AuthError as error:
        raise ApiError(400, ErrorCode.VALIDATION_ERROR, str(error)) from error
    return Response(status_code=204)


@router.post("/auth/email/verification/resend", response_model=EmailVerificationResendResponse)
def email_verification_resend(
    http_request: Request,
    limiter: Annotated[InMemoryAuthLimiter, Depends(get_auth_limiter)],
    user: Annotated[ProductUser, Depends(get_current_user)],
    connection: Annotated[Connection, Depends(get_transaction)],
) -> EmailVerificationResendResponse:
    _guard_auth(limiter, AuthAction.RESEND, _client(http_request), user.user_id)
    try:
        delivery_state = resend_email_verification(connection, user)
        return EmailVerificationResendResponse(delivery_state=delivery_state)
    except AuthError as error:
        raise ApiError(400, ErrorCode.VALIDATION_ERROR, str(error)) from error


@router.post("/auth/external/{provider}", response_model=SessionResponse)
def external_login(
    provider: str,
    request: ExternalAuthRequest,
    connection: Annotated[Connection, Depends(get_transaction)],
) -> SessionResponse:
    provider = provider.upper()
    if provider not in {"APPLE", "GOOGLE"}:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, "Unsupported identity provider")
    try:
        if provider == "APPLE":
            identity = UnconfiguredAppleIdentityVerifier().verify(request.provider_token)
        else:
            identity = UnconfiguredGoogleIdentityVerifier().verify(request.provider_token)
        return _session(
            authenticate_external(connection, provider, identity.subject, identity.email)
        )
    except AuthError as error:
        if "EMAIL_IDENTITY_COLLISION" in str(error):
            raise ApiError(409, ErrorCode.CONFLICT, "EMAIL_IDENTITY_COLLISION") from error
        raise ApiError(401, ErrorCode.UNAUTHORIZED, str(error)) from error
    except RuntimeError as error:
        raise ApiError(
            503,
            ErrorCode.EXTERNAL_ACTIVATION_REQUIRED,
            "Identity provider requires external activation",
        ) from error
    raise ApiError(503, ErrorCode.SERVICE_UNAVAILABLE, "Identity provider unavailable")


@router.post("/auth/refresh", response_model=SessionResponse)
def session_refresh(
    request: RefreshRequest,
    http_request: Request,
    limiter: Annotated[InMemoryAuthLimiter, Depends(get_auth_limiter)],
    connection: Annotated[Connection, Depends(get_transaction)],
) -> SessionResponse:
    _guard_auth(limiter, AuthAction.REFRESH, _client(http_request), request.refresh_token)
    try:
        return _session(refresh_session(connection, request.refresh_token))
    except AuthError as error:
        raise ApiError(
            401, ErrorCode.UNAUTHORIZED, "Refresh token is invalid or expired"
        ) from error


@router.post("/auth/logout", status_code=204)
def session_logout(
    token: Annotated[str, Depends(get_bearer_token)],
    user: Annotated[ProductUser, Depends(get_current_user)],
    connection: Annotated[Connection, Depends(get_transaction)],
) -> Response:
    del user
    logout(connection, token)
    return Response(status_code=204)


@router.post("/auth/account-deletion", response_model=AccountDeletionResponse)
def account_deletion(
    request: AccountDeletionRequest,
    user: Annotated[ProductUser, Depends(get_current_user)],
    connection: Annotated[Connection, Depends(get_transaction)],
) -> AccountDeletionResponse:
    from pitchvalue.product_services.account_deletion import (
        DeletionError,
        initiate_account_deletion,
    )

    try:
        provider_cred_dict = (
            {
                "type": request.provider_credential.credential_type,
                "value": request.provider_credential.credential_value,
            }
            if request.provider_credential
            else None
        )

        from pitchvalue.product_services.entitlements import EntitlementState, resolve_entitlement

        ent = resolve_entitlement(connection, user.user_id)
        has_sub = ent.state in {EntitlementState.PREMIUM_ACTIVE, EntitlementState.PREMIUM_TRIAL}
        sub_provider = ent.source if ent.source != "NONE" else None

        state = initiate_account_deletion(
            connection, user, request.password_or_token, provider_credential=provider_cred_dict
        )
        return AccountDeletionResponse(
            deletion_state=state,
            has_active_store_subscription=has_sub,
            subscription_provider=sub_provider,
        )
    except DeletionError as error:
        raise ApiError(401, ErrorCode.UNAUTHORIZED, str(error)) from error


@router.get("/me", response_model=UserResponse)
def current_user(user: Annotated[ProductUser, Depends(get_current_user)]) -> UserResponse:
    return _user(user)


@router.get("/me/entitlement", response_model=EntitlementResponse)
def current_entitlement(
    user: Annotated[ProductUser, Depends(get_verified_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> EntitlementResponse:
    return EntitlementResponse(**resolve_entitlement(connection, user.user_id).__dict__)


@router.get("/commerce/catalog", response_model=CommerceCatalogResponse)
def commerce_catalog() -> CommerceCatalogResponse:
    return CommerceCatalogResponse(
        state="EXTERNAL_ACTIVATION_REQUIRED",
        plans=("MONTHLY", "THREE_MONTH", "ANNUAL"),
        prices=(),
        trial_eligibility="UNKNOWN",
    )


@router.post("/commerce/verify", response_model=EntitlementResponse)
def verify_purchase(
    request: CommerceVerificationRequestModel,
    user: Annotated[ProductUser, Depends(get_verified_user)],
) -> EntitlementResponse:
    del user
    try:
        ExternalCommerceVerifier().verify(
            CommerceVerificationRequest(
                request.provider,
                request.external_transaction_id,
                request.product_identifier,
                request.plan,
                request.verification_token,
            )
        )
    except RuntimeError as error:
        raise ApiError(
            503,
            ErrorCode.EXTERNAL_ACTIVATION_REQUIRED,
            "Commerce verification requires external activation",
        ) from error
    raise ApiError(503, ErrorCode.SERVICE_UNAVAILABLE, "Commerce verification unavailable")


@router.post("/commerce/restore", response_model=EntitlementResponse)
def restore_purchases(
    user: Annotated[ProductUser, Depends(get_verified_user)],
) -> EntitlementResponse:
    del user
    raise ApiError(
        503,
        ErrorCode.EXTERNAL_ACTIVATION_REQUIRED,
        "Purchase restoration requires external activation",
    )


@router.get("/me/bets", response_model=SavedSelectionListResponse)
def my_bets(
    user: Annotated[ProductUser, Depends(get_verified_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    section: Annotated[str, Query(pattern="^(active|history)$")] = "active",
) -> SavedSelectionListResponse:
    records = list_saved_selections(connection, user.user_id, history=section == "history")
    return SavedSelectionListResponse(
        records=tuple(_saved(item) for item in records), count=len(records)
    )


@router.get("/me/bets/performance", response_model=PerformanceResponse)
def my_bets_performance(
    user: Annotated[ProductUser, Depends(get_verified_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> PerformanceResponse:
    return PerformanceResponse(**performance(connection, user.user_id).__dict__)


@router.get("/me/bets/{saved_selection_id}", response_model=SavedSelectionResponse)
def my_bet(
    saved_selection_id: str,
    user: Annotated[ProductUser, Depends(get_verified_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> SavedSelectionResponse:
    try:
        return _saved(get_saved_selection(connection, user.user_id, saved_selection_id))
    except TrackingError as error:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Tracked selection not found") from error


@router.post("/me/bets", response_model=SavedSelectionResponse, status_code=201)
def save_bet(
    request: SaveSelectionRequest,
    user: Annotated[ProductUser, Depends(get_verified_user)],
    read_connection: Annotated[Connection, Depends(get_connection)],
    write_connection: Annotated[Connection, Depends(get_transaction)],
) -> SavedSelectionResponse:
    candidates = current_predictions(read_connection, [request.match_id], publication_only=True)
    prediction = next(
        (
            item
            for item in candidates
            if item.market == request.market and item.selection == request.selection
        ),
        None,
    )
    if prediction is None:
        raise ApiError(409, ErrorCode.CONFLICT, "Public prediction is unavailable")
    try:
        record = save_public_selection(
            write_connection,
            user_id=user.user_id,
            prediction_snapshot_id=prediction.prediction_snapshot_id,
            line=request.line,
            saved_decimal_odds=request.saved_decimal_odds,
            stake=request.stake,
            currency=request.currency,
        )
    except TrackingError as error:
        raise ApiError(409, ErrorCode.CONFLICT, str(error)) from error
    return _saved(record)


@router.delete("/me/bets/{saved_selection_id}", status_code=204)
def remove_bet(
    saved_selection_id: str,
    user: Annotated[ProductUser, Depends(get_verified_user)],
    connection: Annotated[Connection, Depends(get_transaction)],
) -> Response:
    if not remove_saved_selection(connection, user.user_id, saved_selection_id):
        raise ApiError(404, ErrorCode.NOT_FOUND, "Active tracked selection not found")
    return Response(status_code=204)


@router.get("/ai/best-value", response_model=CouponResponse)
def best_value(
    user: Annotated[ProductUser, Depends(get_verified_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> CouponResponse:
    _require_premium(connection, user)
    records = tuple(published_predictions(connection, limit=4, offset=0))
    contexts = tuple(public_context(item) for item in records)
    state = CouponState.EMPTY if not contexts else CouponState.READY
    return _coupon(CouponResult(state, CouponRisk.BALANCED, 4, contexts))


@router.post("/ai/explain", response_model=AssistantResponse)
def explain_pick(
    request: ExplainRequest,
    user: Annotated[ProductUser, Depends(get_verified_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> AssistantResponse:
    _require_premium(connection, user)
    record = next(
        (
            item
            for item in current_predictions(connection, [request.match_id], publication_only=True)
            if item.market == request.market and item.selection == request.selection
        ),
        None,
    )
    return _assistant(
        explain_public_prediction(record, ExternalAssistantAdapter(), question=request.question)
    )


@router.post("/ai/ask", response_model=AssistantResponse)
def ask_pitchvalue(
    request: AskRequest,
    user: Annotated[ProductUser, Depends(get_verified_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> AssistantResponse:
    _require_premium(connection, user)
    if request.match_id is None or request.market is None or request.selection is None:
        return _assistant(unsupported_prediction_request())
    return explain_pick(
        ExplainRequest(
            match_id=request.match_id,
            market=request.market,
            selection=request.selection,
            question=request.question,
        ),
        user,
        connection,
    )


@router.post("/coupon-builder", response_model=CouponResponse)
def coupon_builder(
    request: CouponRequest,
    user: Annotated[ProductUser, Depends(get_verified_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> CouponResponse:
    _require_premium(connection, user)
    try:
        risk = CouponRisk(request.risk)
    except ValueError as error:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, "Unsupported coupon risk") from error
    records = tuple(published_predictions(connection, limit=100, offset=0))
    return _coupon(build_coupon(records, risk=risk, requested_count=request.requested_count))


@router.get("/product-services/readiness", response_model=ServiceReadinessResponse)
def product_service_readiness(
    connection: Annotated[Connection, Depends(get_connection)],
) -> ServiceReadinessResponse:
    result = validate_product_service_readiness(connection)
    return ServiceReadinessResponse(
        AUTH_READY=result.AUTH_READY.value,
        ENTITLEMENT_READY=result.ENTITLEMENT_READY.value,
        COMMERCE_ACTIVATION_READY=result.COMMERCE_ACTIVATION_READY.value,
        MY_BETS_READY=result.MY_BETS_READY.value,
        AI_CONTRACT_READY=result.AI_CONTRACT_READY.value,
        COUPON_BUILDER_READY=result.COUPON_BUILDER_READY.value,
    )


def _require_premium(connection: Connection, user: ProductUser) -> None:
    entitlement = resolve_entitlement(connection, user.user_id)
    if entitlement.state not in {
        EntitlementState.PREMIUM_ACTIVE,
        EntitlementState.PREMIUM_TRIAL,
    }:
        raise ApiError(403, ErrorCode.FORBIDDEN, "Premium entitlement required")


def _guard_auth(
    limiter: InMemoryAuthLimiter,
    action: AuthAction,
    client: str,
    principal: str = "",
) -> None:
    try:
        limiter.check(action, client, principal)
    except AuthRateLimited as error:
        raise ApiError(
            429,
            ErrorCode.RATE_LIMITED,
            "Too many authentication attempts",
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from error


def _client(request: Request) -> str:
    return "unknown" if request.client is None else request.client.host


def _user(user: ProductUser) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        account_kind=user.account_kind.value,
        email=user.email,
        email_verified=user.email_verified,
    )


def _session(value: IssuedSession) -> SessionResponse:
    return SessionResponse(
        user=_user(value.user),
        access_token=value.access_token,
        refresh_token=value.refresh_token,
        access_expires_at=value.access_expires_at,
        refresh_expires_at=value.refresh_expires_at,
    )


def _saved(value: SavedSelection) -> SavedSelectionResponse:
    return SavedSelectionResponse(
        saved_selection_id=value.saved_selection_id,
        match_id=value.match_id,
        market=value.market,
        selection=value.selection,
        line=value.line,
        saved_decimal_odds=value.saved_decimal_odds,
        stake=value.stake,
        currency=value.currency,
        tracking_status=value.tracking_status.value,
        outcome=None if value.outcome is None else value.outcome.value,
        created_at=value.created_at,
    )


def _context(value: object) -> PublicContextResponse:
    return PublicContextResponse(**value.__dict__)


def _assistant(value: object) -> AssistantResponse:
    return AssistantResponse(
        state=value.state.value,  # type: ignore[attr-defined]
        answer=value.answer,  # type: ignore[attr-defined]
        context=None if value.context is None else _context(value.context),  # type: ignore[attr-defined]
    )


def _coupon(value: object) -> CouponResponse:
    return CouponResponse(
        state=value.state.value,  # type: ignore[attr-defined]
        risk=value.risk.value,  # type: ignore[attr-defined]
        requested_count=value.requested_count,  # type: ignore[attr-defined]
        selections=tuple(_context(item) for item in value.selections),  # type: ignore[attr-defined]
    )
