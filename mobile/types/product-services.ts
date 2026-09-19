export type ProductUser = Readonly<{
  user_id: string;
  account_kind: 'GUEST' | 'AUTHENTICATED';
  email: string | null;
}>;

export type ProductSession = Readonly<{
  user: ProductUser;
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  access_expires_at: string;
  refresh_expires_at: string;
}>;

export type RegistrationResponse = Readonly<{
  session: ProductSession;
  delivery_state: string;
}>;

export type ServerEntitlement = Readonly<{
  state:
    | 'GUEST'
    | 'PREMIUM_ACTIVE'
    | 'PREMIUM_TRIAL'
    | 'PREMIUM_EXPIRED'
    | 'PREMIUM_INACTIVE';
  source: string;
  product_identifier: string | null;
  starts_at: string | null;
  ends_at: string | null;
  trial: boolean;
}>;

export type SavedSelection = Readonly<{
  saved_selection_id: string;
  match_id: number;
  market: string;
  selection: string;
  line: string | null;
  saved_decimal_odds: string | null;
  stake: string | null;
  currency: string | null;
  tracking_status: 'ACTIVE' | 'SETTLED' | 'REMOVED' | 'REVIEW_REQUIRED';
  outcome: 'WON' | 'LOST' | 'VOID' | 'WITHDRAWN' | null;
  created_at: string;
}>;

export type SavedSelectionList = Readonly<{
  records: readonly SavedSelection[];
  count: number;
}>;

export type TrackingPerformance = Readonly<{
  tracked: number;
  wins: number;
  losses: number;
  voids: number;
  withdrawn: number;
  total_stake: string | null;
  net_return: string | null;
  roi: string | null;
}>;

export type ProductServiceReadiness = Readonly<{
  AUTH_READY: string;
  ENTITLEMENT_READY: string;
  COMMERCE_ACTIVATION_READY: string;
  MY_BETS_READY: string;
  AI_CONTRACT_READY: string;
  COUPON_BUILDER_READY: string;
}>;

export type PublicAssistantContext = Readonly<{
  match_id: number;
  market: string;
  selection: string;
  publication_state: string;
  model_probability: string;
  bet_score: string | null;
  edge: string | null;
  final_check: string;
  limitations: readonly string[];
}>;

export type AssistantExecution = Readonly<{
  state:
    | 'AVAILABLE'
    | 'NO_PUBLIC_ANALYSIS'
    | 'EXTERNAL_ACTIVATION_REQUIRED'
    | 'UNSUPPORTED';
  answer: string | null;
  context: PublicAssistantContext | null;
}>;

export type CouponExecution = Readonly<{
  state: 'READY' | 'INSUFFICIENT_ELIGIBLE_POOL' | 'EMPTY';
  risk: 'SAFE' | 'BALANCED' | 'BOLD';
  requested_count: number;
  selections: readonly PublicAssistantContext[];
}>;
