// Tiny in-memory stale-while-revalidate cache for tab screens.
//
// Tab screens refresh their data on every focus so nothing goes stale, but
// refetching used to start with setLoading(true), which blanked the screen to
// a spinner on every tab switch. Screens now seed their state from this cache
// and only show a spinner when there is nothing cached yet; refreshes happen
// silently in the background and update the UI when they land.
//
// The cache is per-session and in-memory only: nothing is persisted, and it is
// cleared on sign-out so data never leaks between accounts.

const cache = new Map<string, unknown>();

export function getScreenCache<T>(key: string): T | undefined {
  return cache.get(key) as T | undefined;
}

export function setScreenCache<T>(key: string, value: T): void {
  cache.set(key, value);
}

export function clearScreenCache(): void {
  cache.clear();
}
