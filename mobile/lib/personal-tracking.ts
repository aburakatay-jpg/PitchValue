export type ContractCapability =
  | 'SUPPORTED'
  | 'PARTIALLY_SUPPORTED'
  | 'MISSING'
  | 'BLOCKED_BY_AUTH'
  | 'BLOCKED_BY_PRODUCT_DECISION';

export const personalTrackingContract = {
  saveMatch: 'MISSING',
  savePrediction: 'MISSING',
  trackedSelection: 'MISSING',
  userOwnership: 'BLOCKED_BY_AUTH',
  guestPersistence: 'BLOCKED_BY_PRODUCT_DECISION',
  guestMigration: 'BLOCKED_BY_PRODUCT_DECISION',
  activeRecords: 'MISSING',
  historyRecords: 'MISSING',
  settlement: 'MISSING',
  resultStates: 'MISSING',
  stake: 'MISSING',
  oddsAtSave: 'MISSING',
  returnOrPayout: 'MISSING',
  roiInputs: 'MISSING',
  changedAnalysisLink: 'MISSING',
  withdrawnAnalysisLink: 'MISSING',
} as const satisfies Readonly<Record<string, ContractCapability>>;

export const productionTrackingAvailable = false;
