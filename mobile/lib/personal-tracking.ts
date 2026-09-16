export type ContractCapability =
  | 'SUPPORTED'
  | 'PARTIALLY_SUPPORTED'
  | 'MISSING'
  | 'BLOCKED_BY_AUTH'
  | 'BLOCKED_BY_PRODUCT_DECISION';

export const personalTrackingContract = {
  saveMatch: 'MISSING',
  savePrediction: 'SUPPORTED',
  trackedSelection: 'SUPPORTED',
  userOwnership: 'SUPPORTED',
  guestPersistence: 'PARTIALLY_SUPPORTED',
  guestMigration: 'BLOCKED_BY_PRODUCT_DECISION',
  activeRecords: 'SUPPORTED',
  historyRecords: 'SUPPORTED',
  settlement: 'SUPPORTED',
  resultStates: 'SUPPORTED',
  stake: 'SUPPORTED',
  oddsAtSave: 'SUPPORTED',
  returnOrPayout: 'PARTIALLY_SUPPORTED',
  roiInputs: 'SUPPORTED',
  changedAnalysisLink: 'MISSING',
  withdrawnAnalysisLink: 'MISSING',
} as const satisfies Readonly<Record<string, ContractCapability>>;

export const productTrackingContractReady = true;
export const productionTrackingAvailable = false;
