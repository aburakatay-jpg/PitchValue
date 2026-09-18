export type CanonicalPlan = 'monthly' | 'quarterly' | 'annual';
export type CommerceProvider = 'APPLE' | 'GOOGLE' | 'UNCONFIGURED';

export interface CommerceProduct {
  id: CanonicalPlan;
  externalId: string;
  provider: CommerceProvider;
  localizedPrice: string | null;
  currencyCode: string | null;
  isTrialAvailable: boolean;
}

export interface CommerceTransaction {
  provider: CommerceProvider;
  externalTransactionId: string;
  receiptData: string; // The base64 payload to send to backend verify
}

export interface CommerceAdapter {
  isConfigured: boolean;
  queryProducts: () => Promise<CommerceProduct[]>;
  purchase: (plan: CanonicalPlan) => Promise<CommerceTransaction>;
  restore: () => Promise<CommerceTransaction[]>;
}

// A fail-closed implementation for when the native environment is unavailable
// or native dependencies (e.g., expo-iap) have not yet been installed.
export class UnconfiguredNativeStoreAdapter implements CommerceAdapter {
  isConfigured = false;

  async queryProducts(): Promise<CommerceProduct[]> {
    return [
      {
        id: 'monthly',
        externalId: 'unconfigured_monthly',
        provider: 'UNCONFIGURED',
        localizedPrice: null,
        currencyCode: null,
        isTrialAvailable: false,
      },
      {
        id: 'quarterly',
        externalId: 'unconfigured_quarterly',
        provider: 'UNCONFIGURED',
        localizedPrice: null,
        currencyCode: null,
        isTrialAvailable: false,
      },
      {
        id: 'annual',
        externalId: 'unconfigured_annual',
        provider: 'UNCONFIGURED',
        localizedPrice: null,
        currencyCode: null,
        isTrialAvailable: false,
      },
    ];
  }

  async purchase(plan: CanonicalPlan): Promise<CommerceTransaction> {
    return Promise.reject(
      new Error(
        'Native store boundary is unconfigured. A signed build with native billing is required.',
      ),
    );
  }

  async restore(): Promise<CommerceTransaction[]> {
    return Promise.reject(
      new Error(
        'Native store boundary is unconfigured. A signed build with native billing is required.',
      ),
    );
  }
}

// Default export uses the unconfigured adapter until a real one is provided
export const defaultCommerceAdapter = new UnconfiguredNativeStoreAdapter();
