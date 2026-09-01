import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { storage } from "@/src/utils/storage";
import { authedFetch } from "@/src/auth";

const STORE_KEY = "reminders_settings_v1";
const FAST_CATEGORY_ID = "rehyn-fast-access";
const FAST_NOTIFICATION_ID = "rehyn-fast-quick-access";
export const FAST_ACTION_ID = "open-fast";

export type ReminderSettings = {
  enabled: boolean;
  dailyHour: number;
  dailyMinute: number;
  weeklyDay: number; // 1=Mon .. 7=Sun
  fastShortcutEnabled: boolean;
};

export const DEFAULT_SETTINGS: ReminderSettings = {
  enabled: true,
  dailyHour: 9,
  dailyMinute: 0,
  weeklyDay: 1,
  fastShortcutEnabled: false,
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

export async function initializeNotificationActions() {
  if (Platform.OS === "web") return;
  try {
    await Notifications.setNotificationCategoryAsync(FAST_CATEGORY_ID, [
      {
        identifier: FAST_ACTION_ID,
        buttonTitle: "Start FAST check",
        options: { opensAppToForeground: true },
      },
    ]);
  } catch {
    // Notification actions can be unavailable in preview clients.
  }
}

export async function configureFastQuickAccess(enabled: boolean) {
  if (Platform.OS === "web") return;
  try {
    await Notifications.cancelScheduledNotificationAsync(FAST_NOTIFICATION_ID);
  } catch {
    // It may already be absent.
  }
  try {
    await Notifications.dismissNotificationAsync(FAST_NOTIFICATION_ID);
  } catch {
    // It may already be absent.
  }
  if (!enabled) return;

  await initializeNotificationActions();
  const allowed = await ensurePermission();
  if (!allowed) return;
  try {
    await Notifications.scheduleNotificationAsync({
      identifier: FAST_NOTIFICATION_ID,
      content: {
        title: "FAST check quick access",
        body: "Tap if you need to check Face, Arms and Speech.",
        sound: false,
        sticky: Platform.OS === "android",
        autoDismiss: false,
        categoryIdentifier: FAST_CATEGORY_ID,
        data: { route: "/emergency" },
      } as any,
      trigger: null,
    });
  } catch {
    // The Settings screen explains when the platform cannot keep this notification visible.
  }
}

type AdaptiveReminderPlan = {
  survey?: { due?: boolean; due_at?: string; patient_prompt_enabled?: boolean };
  assessment?: { due?: boolean; due_at?: string; blocked_by_safety?: boolean };
  exercise_plan?: { action?: string; approved_exercise_ids?: string[] };
};

function futureReminderDate(value?: string): Date | null {
  const parsed = value ? new Date(value) : null;
  if (!parsed || Number.isNaN(parsed.getTime())) return null;
  return parsed.getTime() > Date.now() + 60_000 ? parsed : new Date(Date.now() + 60_000);
}

export async function rescheduleReminders(s: ReminderSettings, suppliedPlan?: AdaptiveReminderPlan | null) {
  if (Platform.OS === "web") return;
  try {
    await Notifications.cancelAllScheduledNotificationsAsync();
    if (!s.enabled) return;

    let plan = suppliedPlan || null;
    if (!plan) {
      try {
        const response = await authedFetch("/api/alira/care-plan");
        if (response.ok) plan = await response.json();
      } catch {
        // Use the conservative legacy schedule when the adaptive plan cannot load.
      }
    }

    const hasAssignedExercises = !plan || (plan.exercise_plan?.approved_exercise_ids?.length || 0) > 0;
    if (hasAssignedExercises && plan?.exercise_plan?.action !== "hold") {
      await Notifications.scheduleNotificationAsync({
        identifier: "daily_exercise",
        content: {
          title: "Rehyn · Today's plan",
          body: "Your guided recovery plan is ready when you are.",
          sound: true,
          data: { route: "/" },
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.CALENDAR,
          hour: s.dailyHour,
          minute: s.dailyMinute,
          repeats: true,
        } as any,
      });
    }

    const surveyDate = plan?.survey?.patient_prompt_enabled === false
      ? null
      : futureReminderDate(plan?.survey?.due_at);
    if (surveyDate) {
      await Notifications.scheduleNotificationAsync({
        identifier: "adaptive_recovery_check_in",
        content: {
          title: "Rehyn · Short recovery check-in",
          body: "Alira has a few short questions to keep your next plan relevant.",
          sound: true,
          data: { route: "/chat" },
        },
        trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: surveyDate } as any,
      });
    }

    const assessmentDate = plan?.assessment?.blocked_by_safety ? null : futureReminderDate(plan?.assessment?.due_at);
    if (assessmentDate) {
      await Notifications.scheduleNotificationAsync({
        identifier: "adaptive_movement_assessment",
        content: {
          title: "Rehyn · Movement check",
          body: "Your next short movement assessment is ready.",
          sound: true,
          data: { route: "/" },
        },
        trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: assessmentDate } as any,
      });
    }

    if (!plan) {
      await Notifications.scheduleNotificationAsync({
        identifier: "weekly_assessment",
        content: {
          title: "Rehyn · Movement check-in",
          body: "Reconnect with Alira to refresh your recovery schedule.",
          sound: true,
          data: { route: "/chat" },
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.CALENDAR,
          weekday: s.weeklyDay,
          hour: s.dailyHour,
          minute: s.dailyMinute,
          repeats: true,
        } as any,
      });
    }
    if (s.fastShortcutEnabled) await configureFastQuickAccess(true);
  } catch {
    // Silent — local notifications may be limited in Expo Go on iOS
  }
}
