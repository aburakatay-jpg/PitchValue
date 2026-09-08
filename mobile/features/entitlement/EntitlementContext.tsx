import { createContext, type PropsWithChildren, useContext } from 'react';

import type { EntitlementState } from '@/types/entitlement';

type EntitlementContextValue = {
  state: EntitlementState;
  openPaywall: () => void;
};

const EntitlementContext = createContext<EntitlementContextValue>({
  state: 'GUEST',
  openPaywall: () => undefined,
});

export function EntitlementProvider({
  children,
  state = 'GUEST',
  openPaywall = () => undefined,
}: PropsWithChildren<Partial<EntitlementContextValue>>) {
  return (
    <EntitlementContext.Provider value={{ state, openPaywall }}>
      {children}
    </EntitlementContext.Provider>
  );
}

export function useEntitlement(): EntitlementContextValue {
  return useContext(EntitlementContext);
}
