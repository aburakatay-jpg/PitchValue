import React, { createContext, useContext, useEffect, useState } from 'react';

import { useProductSession } from '@/features/session/ProductSessionContext';
import {
  CanonicalPlan,
  CommerceAdapter,
  CommerceProduct,
  defaultCommerceAdapter,
} from '@/lib/commerce';
import { restorePurchases, verifyPurchase } from '@/lib/product-api';

interface CommerceContextValue {
  isConfigured: boolean;
  products: CommerceProduct[];
  isFetchingProducts: boolean;
  isPurchasing: boolean;
  isRestoring: boolean;
  error: Error | null;
  purchase: (plan: CanonicalPlan) => Promise<void>;
  restore: () => Promise<void>;
}

const CommerceContext = createContext<CommerceContextValue | null>(null);

export function CommerceProvider({
  children,
  adapter = defaultCommerceAdapter,
}: {
  children: React.ReactNode;
  adapter?: CommerceAdapter;
}) {
  const session = useProductSession();
  const token = session.state === 'AUTHENTICATED' ? session.accessToken : null;
  const refreshEntitlement = session.refreshEntitlement;
  const [products, setProducts] = useState<CommerceProduct[]>([]);
  const [isFetchingProducts, setIsFetchingProducts] = useState(false);
  const [isPurchasing, setIsPurchasing] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let mounted = true;
    const fetchProducts = async () => {
      setIsFetchingProducts(true);
      try {
        const fetchedProducts = await adapter.queryProducts();
        if (mounted) setProducts(fetchedProducts);
      } catch (err) {
        if (mounted)
          setError(err instanceof Error ? err : new Error(String(err)));
      } finally {
        if (mounted) setIsFetchingProducts(false);
      }
    };
    void fetchProducts();
    return () => {
      mounted = false;
    };
  }, [adapter]);

  const purchase = async (plan: CanonicalPlan) => {
    if (!token) return;
    setIsPurchasing(true);
    setError(null);
    try {
      const transaction = await adapter.purchase(plan);
      const controller = new AbortController();
      // Server verification
      await verifyPurchase(
        token,
        {
          provider: transaction.provider,
          external_transaction_id: transaction.externalTransactionId,
          receipt_data: transaction.receiptData,
        },
        controller.signal,
      );
      await refreshEntitlement();
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      throw err;
    } finally {
      setIsPurchasing(false);
    }
  };

  const restore = async () => {
    if (!token) return;
    setIsRestoring(true);
    setError(null);
    try {
      const transactions = await adapter.restore();
      if (transactions.length > 0) {
        // Optimistically use the most recent or all. The backend restore API takes one evidence token.
        // Usually iOS provides one latest app receipt, Google provides multiple.
        const transaction = transactions[0];
        if (transaction) {
          const controller = new AbortController();
          await restorePurchases(
            token,
            {
              provider: transaction.provider,
              receipt_data: transaction.receiptData,
            },
            controller.signal,
          );
        }
      }
      await refreshEntitlement();
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      throw err;
    } finally {
      setIsRestoring(false);
    }
  };

  return (
    <CommerceContext.Provider
      value={{
        isConfigured: adapter.isConfigured,
        products,
        isFetchingProducts,
        isPurchasing,
        isRestoring,
        error,
        purchase,
        restore,
      }}
    >
      {children}
    </CommerceContext.Provider>
  );
}

export function useCommerce(): CommerceContextValue {
  const context = useContext(CommerceContext);
  if (!context) {
    throw new Error('useCommerce must be used within a CommerceProvider');
  }
  return context;
}
