import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";

import { API_BASE as BASE } from "@/src/config";
import { authedFetch } from "@/src/auth";
import { loadUserPreferences } from "@/src/userPreferences";
import { storage } from "@/src/utils/storage";
import { colors, radius, spacing } from "@/src/theme";
import { SafetyStopStrip } from "@/src/components/SafetyStopStrip";
import { PointsCelebration, PointsCelebrationEvent, celebrationEvent } from "@/src/components/PointsCelebration";
import { localDateString } from "@/src/components/DailyCheckInCalendar";

type GameProgress = {
  completed: boolean;
  checkpoints: number;
  total: number;
  sessions: number;
  last_completed_at?: string;
};

const GAME_PROGRESS_KEY = (planId: string, gameId: string) => `rehab_game_progress_v1:${planId}:${gameId}`;

export default function RehabGameScreen() {
  const router = useRouter();
  const { game_id, name, plan_id, difficulty } = useLocalSearchParams<{
    game_id: string;
    name?: string;
    plan_id?: string;
    difficulty?: string;
  }>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [voiceGuidance, setVoiceGuidance] = useState(true);
  const [celebration, setCelebration] = useState<PointsCelebrationEvent | null>(null);

  const gameId = game_id || "garden_reach";
  const planId = plan_id || "default";
  const selectedDifficulty = difficulty === "easy" || difficulty === "difficult" ? difficulty : "medium";
  const url = `${BASE}/api/rehab/game-runner?game_id=${encodeURIComponent(gameId)}&difficulty=${selectedDifficulty}&voice_guidance=${voiceGuidance ? "1" : "0"}`;

  useEffect(() => {
    void loadUserPreferences().then((saved) => setVoiceGuidance(saved.voiceGuidance));
  }, []);

  const saveCheckpoint = async (checkpoints: number, total: number) => {
    try {
      const raw = await storage.getItem(GAME_PROGRESS_KEY(planId, gameId), "");
      const previous: GameProgress = raw
        ? JSON.parse(raw)
        : { completed: false, checkpoints: 0, total, sessions: 0 };
      const next: GameProgress = {
        ...previous,
        checkpoints: Math.max(previous.checkpoints || 0, checkpoints),
        total,
      };
      await storage.setItem(GAME_PROGRESS_KEY(planId, gameId), JSON.stringify(next));
    } catch {
      // The game remains playable if local storage is temporarily unavailable.
    }
  };

  const completeGame = async (completed: number, total: number) => {
    const completedAt = new Date().toISOString();
    try {
      const raw = await storage.getItem(GAME_PROGRESS_KEY(planId, gameId), "");
      const previous: GameProgress = raw
        ? JSON.parse(raw)
        : { completed: false, checkpoints: 0, total, sessions: 0 };
      await storage.setItem(GAME_PROGRESS_KEY(planId, gameId), JSON.stringify({
        completed: true,
        checkpoints: completed,
        total,
        sessions: (previous.sessions || 0) + 1,
        last_completed_at: completedAt,
      } satisfies GameProgress));
    } catch {
      // Server activity logging remains independent from local display state.
    }

    try {
      await authedFetch("/api/alira/activities", {
        method: "POST",
        body: JSON.stringify({
          exercise_id: `game_${gameId}`,
          plan_id: planId,
          completed_reps: completed,
          average_score: null,
          completed_at: completedAt,
          activity_type: "rehab_game",
          difficulty: selectedDifficulty,
        }),
      });
      await authedFetch("/api/users/daily-checkin/complete", {
        method: "POST",
        body: JSON.stringify({ date: localDateString() }),
      });
    } catch {
      // Local completion remains visible and can sync during a later session.
    }
  };

  const onMessage = async (event: WebViewMessageEvent) => {
    try {
      const message = JSON.parse(event.nativeEvent.data);
      if (message.type === "ready") {
        setLoading(false);
      } else if (message.type === "game_checkpoint") {
        void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        await saveCheckpoint(Number(message.index || 0), Number(message.total || 0));
      } else if (message.type === "game_complete") {
        void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        const completed = Number(message.completed || 0);
        const total = Number(message.total || completed);
        await completeGame(completed, total);
        setDone(true);
        setCelebration(celebrationEvent(3, "Movement game complete - lovely work!"));
        setTimeout(() => router.back(), 2600);
      } else if (message.type === "camera_error") {
        setError("Camera unavailable. Allow camera access in your phone settings, then try again.");
      } else if (message.type === "exit") {
        router.back();
      }
    } catch {
      // Ignore malformed runner messages.
    }
  };

  return (
    <View style={styles.container}>
      <WebView
        testID="rehab-game-webview"
        source={{ uri: url }}
        style={styles.webview}
        originWhitelist={["*"]}
        javaScriptEnabled
        domStorageEnabled
        mediaPlaybackRequiresUserAction={false}
        allowsInlineMediaPlayback
        {...(Platform.OS === "ios" ? { mediaCapturePermissionGrantType: "grant" as const } : {})}
        {...({ onPermissionRequest: (event: any) => { try { event?.grant(event?.resources || []); } catch {} } } as any)}
        onMessage={onMessage}
        onLoadEnd={() => setLoading(false)}
        onError={(event) => setError(String(event.nativeEvent.description || event.nativeEvent))}
      />

      {loading && (
        <View style={styles.loading} pointerEvents="none">
          <ActivityIndicator size="large" color={colors.brandSecondary} />
          <Text style={styles.loadingText}>Preparing {name || "movement game"}...</Text>
        </View>
      )}

      {done && (
        <View style={styles.done} pointerEvents="none" testID="rehab-game-complete">
          <Ionicons name="checkmark-circle" size={58} color="#75C78B" />
          <Text style={styles.doneTitle}>Game complete</Text>
          <Text style={styles.doneText}>Returning to My Time...</Text>
        </View>
      )}

      {error && (
        <View style={styles.error} testID="rehab-game-error">
          <Ionicons name="camera-outline" size={46} color={colors.brandSecondary} />
          <Text style={styles.errorTitle}>{error}</Text>
          <Pressable onPress={() => router.back()} style={styles.errorButton}>
            <Text style={styles.errorButtonText}>Return to My Time</Text>
          </Pressable>
        </View>
      )}

      <SafetyStopStrip />
      <PointsCelebration event={celebration} onDone={() => setCelebration(null)} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F5F6F2" },
  webview: { flex: 1, backgroundColor: "#F5F6F2" },
  loading: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", gap: spacing.md, backgroundColor: "#F5F6F2" },
  loadingText: { fontSize: 16, lineHeight: 22, fontWeight: "700", color: "#164A36" },
  done: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: "rgba(18,54,38,0.96)" },
  doneTitle: { fontSize: 26, lineHeight: 33, fontWeight: "800", color: "#FFFFFF" },
  doneText: { fontSize: 15, lineHeight: 21, color: "#D9E5DC" },
  error: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.xl, backgroundColor: "rgba(18,25,21,0.97)" },
  errorTitle: { maxWidth: 480, fontSize: 17, lineHeight: 24, textAlign: "center", fontWeight: "700", color: "#FFFFFF" },
  errorButton: { minHeight: 50, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.lg, borderRadius: radius.sm, backgroundColor: colors.brandPrimary },
  errorButtonText: { fontSize: 15, lineHeight: 21, fontWeight: "800", color: "#FFFFFF" },
});
