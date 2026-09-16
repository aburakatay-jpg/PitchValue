import * as SecureStore from 'expo-secure-store';
import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import {
  getCurrentUser,
  getServerEntitlement,
  loginEmail,
  logoutProductSession,
  ProductServiceError,
  refreshProductSession,
  registerEmail,
} from '@/lib/product-api';
import type {
  ProductSession,
  ProductUser,
  ServerEntitlement,
} from '@/types/product-services';

const ACCESS_KEY = 'pitchvalue.product.access.v1';
const REFRESH_KEY = 'pitchvalue.product.refresh.v1';

type SessionState = 'BOOTSTRAPPING' | 'GUEST' | 'AUTHENTICATED' | 'UNAVAILABLE';

type ProductSessionContextValue = Readonly<{
  state: SessionState;
  accessToken: string | null;
  user: ProductUser | null;
  entitlement: ServerEntitlement['state'];
  signInEmail: (email: string, password: string) => Promise<void>;
  signUpEmail: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}>;

const ProductSessionContext = createContext<ProductSessionContextValue | null>(
  null,
);

async function persistSession(session: ProductSession): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_KEY, session.access_token),
    SecureStore.setItemAsync(REFRESH_KEY, session.refresh_token),
  ]);
}

async function clearSession(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_KEY),
    SecureStore.deleteItemAsync(REFRESH_KEY),
  ]);
}

export function ProductSessionProvider({ children }: PropsWithChildren) {
  const [state, setState] = useState<SessionState>('BOOTSTRAPPING');
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<ProductUser | null>(null);
  const [entitlement, setEntitlement] =
    useState<ServerEntitlement['state']>('GUEST');

  const activate = useCallback(async (session: ProductSession) => {
    const controller = new AbortController();
    const serverEntitlement = await getServerEntitlement(
      session.access_token,
      controller.signal,
    );
    await persistSession(session);
    setAccessToken(session.access_token);
    setUser(session.user);
    setEntitlement(serverEntitlement.state);
    setState('AUTHENTICATED');
  }, []);

  useEffect(() => {
    let mounted = true;
    const bootstrap = async () => {
      const [storedAccess, storedRefresh] = await Promise.all([
        SecureStore.getItemAsync(ACCESS_KEY),
        SecureStore.getItemAsync(REFRESH_KEY),
      ]);
      if (!mounted) return;
      if (!storedAccess || !storedRefresh) {
        setState('GUEST');
        return;
      }
      const controller = new AbortController();
      try {
        const current = await getCurrentUser(storedAccess, controller.signal);
        const currentEntitlement = await getServerEntitlement(
          storedAccess,
          controller.signal,
        );
        if (!mounted) return;
        setAccessToken(storedAccess);
        setUser(current);
        setEntitlement(currentEntitlement.state);
        setState('AUTHENTICATED');
      } catch (error) {
        if (
          error instanceof ProductServiceError &&
          error.kind === 'UNAUTHORIZED'
        ) {
          try {
            const refreshed = await refreshProductSession(
              storedRefresh,
              controller.signal,
            );
            if (mounted) await activate(refreshed);
            return;
          } catch {
            await clearSession();
            if (mounted) setState('GUEST');
            return;
          }
        }
        if (mounted) setState('UNAVAILABLE');
      }
    };
    void bootstrap();
    return () => {
      mounted = false;
    };
  }, [activate]);

  const signInEmail = useCallback(
    async (email: string, password: string) => {
      const session = await loginEmail(
        email,
        password,
        new AbortController().signal,
      );
      await activate(session);
    },
    [activate],
  );
  const signUpEmail = useCallback(
    async (email: string, password: string) => {
      const session = await registerEmail(
        email,
        password,
        new AbortController().signal,
      );
      await activate(session);
    },
    [activate],
  );
  const signOut = useCallback(async () => {
    if (accessToken) {
      try {
        await logoutProductSession(accessToken, new AbortController().signal);
      } catch {
        // Local credentials must still be cleared when remote revocation is unavailable.
      }
    }
    await clearSession();
    setAccessToken(null);
    setUser(null);
    setEntitlement('GUEST');
    setState('GUEST');
  }, [accessToken]);

  const value = useMemo(
    () => ({
      state,
      accessToken,
      user,
      entitlement,
      signInEmail,
      signUpEmail,
      signOut,
    }),
    [state, accessToken, user, entitlement, signInEmail, signUpEmail, signOut],
  );
  return (
    <ProductSessionContext.Provider value={value}>
      {children}
    </ProductSessionContext.Provider>
  );
}

export function useProductSession(): ProductSessionContextValue {
  const value = useContext(ProductSessionContext);
  return (
    value ?? {
      state: 'GUEST',
      accessToken: null,
      user: null,
      entitlement: 'GUEST',
      signInEmail: async () => {
        throw new ProductServiceError('UNAVAILABLE');
      },
      signUpEmail: async () => {
        throw new ProductServiceError('UNAVAILABLE');
      },
      signOut: async () => undefined,
    }
  );
}
