import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { storage } from "@/src/utils/storage";

const STORE_KEY = "reminders_settings_v1";

export type ReminderSettings = {
  enabled: boolean;
  dailyHour: number;
  dailyMinute: number;
  weeklyDay: number; // 1=Mon .. 7=Sun
};

export const DEFAULT_SETTINGS: ReminderSettings = {
  enabled: true,
  dailyHour: 9,
  dailyMinute: 0,
  weeklyDay: 1,
};

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export async function ensurePermission(): Promise<boolean> {
  if (Platform.OS === "web") return false;
  const { status } = await Notifications.getPermissionsAsync();
  if (status === "granted") return true;
  const req = await Notifications.requestPermissionsAsync();
  return req.status === "granted";
}

export async function loadSettings(): Promise<ReminderSettings> {
  const raw = await storage.getItem(STORE_KEY, "");
  if (!raw) return DEFAULT_SETTINGS;
  try { return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) }; }
  catch { return DEFAULT_SETTINGS; }
}

export async function saveSettings(s: ReminderSettings) {
  await storage.setItem(STORE_KEY, JSON.stringify(s));
}

export async function rescheduleReminders(s: ReminderSettings) {
  if (Platform.OS === "web") return;
  try {
    await Notifications.cancelAllScheduledNotificationsAsync();
    if (!s.enabled) return;

    // Daily exercise reminder (local notification)
    await Notifications.scheduleNotificationAsync({
      identifier: "daily_exercise",
      content: {
        title: "Hope · Daily check-in",
        body: "Time for today's rehab — even 5 minutes is a real win 💚",
        sound: true,
      },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.CALENDAR,
        hour: s.dailyHour,
        minute: s.dailyMinute,
        repeats: true,
      } as any,
    });

    // Weekly movement check-in reminder
    await Notifications.scheduleNotificationAsync({
      identifier: "weekly_assessment",
      content: {
        title: "Hope · Weekly movement check-in",
        body: "It's time to retake your quick movement assessment. Let's see your progress!",
        sound: true,
      },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.CALENDAR,
        weekday: s.weeklyDay,
        hour: s.dailyHour,
        minute: s.dailyMinute,
        repeats: true,
      } as any,
    });
  } catch {
    // Silent — local notifications may be limited in Expo Go on iOS
  }
}
