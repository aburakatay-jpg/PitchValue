import { config } from '@/lib/config';
import type {
  AssistantExecution,
  CouponExecution,
  ProductServiceReadiness,
  ProductSession,
  ProductUser,
  SavedSelection,
  SavedSelectionList,
  ServerEntitlement,
  TrackingPerformance,
} from '@/types/product-services';

export class ProductServiceError extends Error {
  constructor(
    readonly kind:
      | 'UNAVAILABLE'
      | 'UNAUTHORIZED'
      | 'FORBIDDEN'
      | 'CONFLICT'
      | 'INVALID_RESPONSE',
  ) {
    super('Product service unavailable');
    this.name = 'ProductServiceError';
  }
}

async function productRequest<T>(
  path: string,
  options: Readonly<{
    method?: 'GET' | 'POST' | 'DELETE';
    token?: string;
    body?: unknown;
    signal: AbortSignal;
  }>,
  validator: (value: unknown) => value is T,
): Promise<T> {
  if (config.apiBaseUrl === null) throw new ProductServiceError('UNAVAILABLE');
  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl.replace(/\/$/, '')}${path}`, {
      method: options.method ?? 'GET',
      headers: {
        Accept: 'application/json',
        ...(options.body === undefined
          ? {}
          : { 'Content-Type': 'application/json' }),
        ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      },
      ...(options.body === undefined
        ? {}
        : { body: JSON.stringify(options.body) }),
      signal: options.signal,
    });
  } catch {
    throw new ProductServiceError('UNAVAILABLE');
  }
  if (!response.ok) {
    if (response.status === 401) throw new ProductServiceError('UNAUTHORIZED');
    if (response.status === 403) throw new ProductServiceError('FORBIDDEN');
    if (response.status === 409) throw new ProductServiceError('CONFLICT');
    throw new ProductServiceError('UNAVAILABLE');
  }
  if (response.status === 204) return undefined as T;
  try {
    const payload: unknown = await response.json();
    if (!validator(payload)) throw new ProductServiceError('INVALID_RESPONSE');
    return payload;
  } catch {
    throw new ProductServiceError('INVALID_RESPONSE');
  }
}

export function createGuestSession(
  signal: AbortSignal,
): Promise<ProductSession> {
  return productRequest(
    '/api/v1/auth/guest',
    { method: 'POST', signal },
    isSession,
  );
}

export function registerEmail(
  email: string,
  password: string,
  signal: AbortSignal,
): Promise<ProductSession> {
  return productRequest(
    '/api/v1/auth/email/register',
    { method: 'POST', body: { email, password }, signal },
    isSession,
  );
}

export function loginEmail(
  email: string,
  password: string,
  signal: AbortSignal,
): Promise<ProductSession> {
  return productRequest(
    '/api/v1/auth/email/login',
    { method: 'POST', body: { email, password }, signal },
    isSession,
  );
}

export function refreshProductSession(
  refreshToken: string,
  signal: AbortSignal,
): Promise<ProductSession> {
  return productRequest(
    '/api/v1/auth/refresh',
    { method: 'POST', body: { refresh_token: refreshToken }, signal },
    isSession,
  );
}

export function logoutProductSession(
  token: string,
  signal: AbortSignal,
): Promise<void> {
  return productRequest(
    '/api/v1/auth/logout',
    { method: 'POST', token, signal },
    isVoid,
  );
}

export function getCurrentUser(
  token: string,
  signal: AbortSignal,
): Promise<ProductUser> {
  return productRequest('/api/v1/me', { token, signal }, isUser);
}

export function getServerEntitlement(
  token: string,
  signal: AbortSignal,
): Promise<ServerEntitlement> {
  return productRequest(
    '/api/v1/me/entitlement',
    { token, signal },
    isEntitlement,
  );
}

export function getSavedSelections(
  token: string,
  section: 'active' | 'history',
  signal: AbortSignal,
): Promise<SavedSelectionList> {
  return productRequest(
    `/api/v1/me/bets?section=${section}`,
    { token, signal },
    isSavedList,
  );
}

export function saveSelection(
  token: string,
  value: Readonly<{
    match_id: number;
    market: string;
    selection: string;
    line?: string;
    saved_decimal_odds?: string;
    stake?: string;
    currency?: string;
  }>,
  signal: AbortSignal,
): Promise<SavedSelection> {
  return productRequest(
    '/api/v1/me/bets',
    { method: 'POST', token, body: value, signal },
    isSaved,
  );
}

export function removeSavedSelection(
  token: string,
  savedSelectionId: string,
  signal: AbortSignal,
): Promise<void> {
  return productRequest(
    `/api/v1/me/bets/${encodeURIComponent(savedSelectionId)}`,
    { method: 'DELETE', token, signal },
    isVoid,
  );
}

export function getTrackingPerformance(
  token: string,
  signal: AbortSignal,
): Promise<TrackingPerformance> {
  return productRequest(
    '/api/v1/me/bets/performance',
    { token, signal },
    isPerformance,
  );
}

export function getProductServiceReadiness(
  signal: AbortSignal,
): Promise<ProductServiceReadiness> {
  return productRequest(
    '/api/v1/product-services/readiness',
    { signal },
    isReadiness,
  );
}

export function explainPublishedSelection(
  token: string,
  context: Readonly<{
    match_id: number;
    market: string;
    selection: string;
    question?: string;
  }>,
  signal: AbortSignal,
): Promise<AssistantExecution> {
  return productRequest(
    '/api/v1/ai/explain',
    { method: 'POST', token, body: context, signal },
    isAssistantExecution,
  );
}

export function buildEligibleCoupon(
  token: string,
  risk: 'SAFE' | 'BALANCED' | 'BOLD',
  requestedCount: number,
  signal: AbortSignal,
): Promise<CouponExecution> {
  return productRequest(
    '/api/v1/coupon-builder',
    {
      method: 'POST',
      token,
      body: { risk, requested_count: requestedCount },
      signal,
    },
    isCouponExecution,
  );
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function nullableString(value: unknown): boolean {
  return value === null || typeof value === 'string';
}

function isUser(value: unknown): value is ProductUser {
  return (
    isObject(value) &&
    typeof value.user_id === 'string' &&
    (value.account_kind === 'GUEST' ||
      value.account_kind === 'AUTHENTICATED') &&
    nullableString(value.email)
  );
}

function isSession(value: unknown): value is ProductSession {
  return (
    isObject(value) &&
    isUser(value.user) &&
    typeof value.access_token === 'string' &&
    typeof value.refresh_token === 'string' &&
    value.token_type === 'bearer' &&
    typeof value.access_expires_at === 'string' &&
    typeof value.refresh_expires_at === 'string'
  );
}

function isEntitlement(value: unknown): value is ServerEntitlement {
  return (
    isObject(value) &&
    [
      'GUEST',
      'PREMIUM_ACTIVE',
      'PREMIUM_TRIAL',
      'PREMIUM_EXPIRED',
      'PREMIUM_INACTIVE',
    ].includes(String(value.state)) &&
    typeof value.source === 'string' &&
    nullableString(value.product_identifier) &&
    nullableString(value.starts_at) &&
    nullableString(value.ends_at) &&
    typeof value.trial === 'boolean'
  );
}

function isSaved(value: unknown): value is SavedSelection {
  return (
    isObject(value) &&
    typeof value.saved_selection_id === 'string' &&
    typeof value.match_id === 'number' &&
    typeof value.market === 'string' &&
    typeof value.selection === 'string' &&
    nullableString(value.line) &&
    nullableString(value.saved_decimal_odds) &&
    nullableString(value.stake) &&
    nullableString(value.currency) &&
    typeof value.tracking_status === 'string' &&
    nullableString(value.outcome) &&
    typeof value.created_at === 'string'
  );
}

function isSavedList(value: unknown): value is SavedSelectionList {
  return (
    isObject(value) &&
    Array.isArray(value.records) &&
    value.records.every(isSaved) &&
    typeof value.count === 'number'
  );
}

function isPerformance(value: unknown): value is TrackingPerformance {
  return (
    isObject(value) &&
    ['tracked', 'wins', 'losses', 'voids', 'withdrawn'].every(
      (key) => typeof value[key] === 'number',
    ) &&
    nullableString(value.total_stake) &&
    nullableString(value.net_return) &&
    nullableString(value.roi)
  );
}

function isReadiness(value: unknown): value is ProductServiceReadiness {
  return (
    isObject(value) &&
    [
      'AUTH_READY',
      'ENTITLEMENT_READY',
      'COMMERCE_ACTIVATION_READY',
      'MY_BETS_READY',
      'AI_CONTRACT_READY',
      'COUPON_BUILDER_READY',
    ].every((key) => typeof value[key] === 'string')
  );
}

function isAssistantContext(value: unknown): boolean {
  return (
    isObject(value) &&
    typeof value.match_id === 'number' &&
    typeof value.market === 'string' &&
    typeof value.selection === 'string' &&
    typeof value.publication_state === 'string' &&
    typeof value.model_probability === 'string' &&
    nullableString(value.bet_score) &&
    nullableString(value.edge) &&
    typeof value.final_check === 'string' &&
    Array.isArray(value.limitations) &&
    value.limitations.every((item) => typeof item === 'string')
  );
}

function isAssistantExecution(value: unknown): value is AssistantExecution {
  return (
    isObject(value) &&
    [
      'AVAILABLE',
      'NO_PUBLIC_ANALYSIS',
      'EXTERNAL_ACTIVATION_REQUIRED',
      'UNSUPPORTED',
    ].includes(String(value.state)) &&
    nullableString(value.answer) &&
    (value.context === null || isAssistantContext(value.context))
  );
}

function isCouponExecution(value: unknown): value is CouponExecution {
  return (
    isObject(value) &&
    ['READY', 'INSUFFICIENT_ELIGIBLE_POOL', 'EMPTY'].includes(
      String(value.state),
    ) &&
    ['SAFE', 'BALANCED', 'BOLD'].includes(String(value.risk)) &&
    typeof value.requested_count === 'number' &&
    Array.isArray(value.selections) &&
    value.selections.every(isAssistantContext)
  );
}

function isVoid(value: unknown): value is void {
  return value === undefined;
}

export function verifyPurchase(
  token: string,
  evidence: Readonly<{
    provider: string;
    external_transaction_id: string;
    receipt_data: string;
  }>,
  signal: AbortSignal,
): Promise<ServerEntitlement> {
  return productRequest(
    '/api/v1/commerce/verify',
    { method: 'POST', token, body: evidence, signal },
    isEntitlement,
  );
}

export function restorePurchases(
  token: string,
  evidence: Readonly<{
    provider: string;
    receipt_data: string;
  }>,
  signal: AbortSignal,
): Promise<ServerEntitlement> {
  return productRequest(
    '/api/v1/commerce/restore',
    { method: 'POST', token, body: evidence, signal },
    isEntitlement,
  );
}
