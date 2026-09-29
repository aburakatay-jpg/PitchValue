import { useState, useEffect, useCallback } from 'react';
import { getFollowedMatches, followMatch, unfollowMatch } from '@/lib/product-api';
import { useProductSession } from '@/features/session/ProductSessionContext';

export function useFollow(matchId: number) {
  const { user, accessToken } = useProductSession();
  const [isFollowed, setIsFollowed] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const isAuthenticated = user?.account_kind === 'AUTHENTICATED';
  const token = accessToken;

  useEffect(() => {
    if (!isAuthenticated || !token) return;
    const controller = new AbortController();
    
    setIsLoading(true);
    getFollowedMatches(token, controller.signal)
      .then(follows => {
        setIsFollowed(follows.includes(matchId));
        setError(null);
      })
      .catch(err => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setIsLoading(false));

    return () => controller.abort();
  }, [matchId, isAuthenticated, token]);

  const toggleFollow = useCallback(async () => {
    if (!isAuthenticated || !token) return;
    
    setIsLoading(true);
    setError(null);
    try {
      if (isFollowed) {
        await unfollowMatch(token, matchId);
        setIsFollowed(false);
      } else {
        await followMatch(token, matchId);
        setIsFollowed(true);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [matchId, isAuthenticated, token, isFollowed]);

  return { isFollowed, isLoading, error, toggleFollow, isAuthenticated };
}
