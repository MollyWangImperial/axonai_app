import AsyncStorage from "@react-native-async-storage/async-storage";
import { clearScreenCache } from "@/src/screenCache";

export const accountGenerationKey = (userId: string) => `account_generation_v1:${userId}`;

export function belongsToResetAccount(key: string, userId: string): boolean {
  if (key === `pending_account_reset_v1:${userId}`) return false;
  return key.split(":").some((part) => part === userId || part === encodeURIComponent(userId));
}

export async function clearAccountJourneyCache(userId: string) {
  // Only persisted keys explicitly owned by this account. Leave global device
  // preferences and other accounts untouched. screenCache is memory-only.
  const keys = (await AsyncStorage.getAllKeys()).filter((key) => belongsToResetAccount(key, userId));
  if (keys.length) await AsyncStorage.multiRemove(keys);
  clearScreenCache();
}
