import { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Platform } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { storage } from "@/src/utils/storage";
import { SafetyStopStrip } from "@/src/components/SafetyStopStrip";
import { localDateString } from "@/src/components/DailyCheckInCalendar";
import { API_BASE as BASE } from "@/src/config";
import { loadUserPreferences } from "@/src/userPreferences";
import { authedFetch } from "@/src/auth";

type ExerciseProgress = {
  completed_reps: number;
  total_reps: number;
  last_score: number | null;
  best_score: number | null;
  sessions: number;
  last_session_scores?: number[];
  score_history?: { completed_at: string; average_score: number; repetition_scores: number[] }[];
};

const PROGRESS_KEY = (planId: string, exId: string) => `ex_progress_v1:${planId}:${exId}`;

export default function ExerciseScreen() {
  const router = useRouter();
  const { exercise_id, name, plan_id, sets, reps, difficulty, variation, affected_side, rehab_session_id, library_test } = useLocalSearchParams<{ exercise_id: string; name?: string; plan_id?: string; sets?: string; reps?: string; difficulty?: string; variation?: string; affected_side?: string; rehab_session_id?: string; library_test?: string }>();
  const webRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [doneInfo, setDoneInfo] = useState<{ reps: number; avgScore: number | null } | null>(null);
  const [voiceGuidance, setVoiceGuidance] = useState(true);
  const scoresThisSession = useRef<number[]>([]);

  const totalSets = parseInt(sets || "3", 10);
  const totalReps = parseInt(reps || "10", 10);
  const totalAll = totalSets * totalReps;
  const planId = plan_id || "default";
  const isLibraryTest = library_test === "1";

  const guidedReps = Math.max(1, Math.min(20, totalReps));
  const sessionDifficulty = difficulty === "easy" || difficulty === "difficult" ? difficulty : "medium";
  const sessionVariation = variation === "alternate" ? "alternate" : "standard";
  const affectedSide = affected_side === "left" ? "left" : "right";
  const rehabSessionId = typeof rehab_session_id === "string" ? rehab_session_id : "";
  const url = `${BASE}/api/rehab/runner?exercise_id=${encodeURIComponent(exercise_id || "ex_maintenance")}&reps=${guidedReps}&difficulty=${sessionDifficulty}&variation=${sessionVariation}&affected_side=${affectedSide}&rehab_session_id=${encodeURIComponent(rehabSessionId)}&voice_guidance=${voiceGuidance ? "1" : "0"}`;

  useEffect(() => {
    void loadUserPreferences().then((saved) => setVoiceGuidance(saved.voiceGuidance));
  }, []);

  const saveRepProgress = async (newReps: number) => {
    if (isLibraryTest) return;
    if (!exercise_id) return;
    try {
      const raw = await storage.getItem(PROGRESS_KEY(planId, exercise_id), "");
      const prev: ExerciseProgress = raw
        ? JSON.parse(raw)
        : { completed_reps: 0, total_reps: totalAll, last_score: null, best_score: null, sessions: 0 };
      const updated: ExerciseProgress = {
        completed_reps: Math.min(totalAll, prev.completed_reps + newReps),
        total_reps: totalAll,
        last_score: prev.last_score,
        best_score: prev.best_score,
        sessions: prev.sessions,
        last_session_scores: prev.last_session_scores,
        score_history: prev.score_history,
      };
      await storage.setItem(PROGRESS_KEY(planId, exercise_id), JSON.stringify(updated));
    } catch {/* */}
  };

  const saveSessionAverage = async (averageScore: number | null, repetitionScores: number[]) => {
    if (isLibraryTest || !exercise_id) return;
    try {
      const raw = await storage.getItem(PROGRESS_KEY(planId, exercise_id), "");
      const prev: ExerciseProgress = raw
        ? JSON.parse(raw)
        : { completed_reps: 0, total_reps: totalAll, last_score: null, best_score: null, sessions: 0 };
      const completedAt = new Date().toISOString();
      const scoreHistory = averageScore == null
        ? prev.score_history || []
        : [
            ...(prev.score_history || []),
            { completed_at: completedAt, average_score: averageScore, repetition_scores: repetitionScores },
          ].slice(-60);
      const updated: ExerciseProgress = {
        ...prev,
        total_reps: totalAll,
        last_score: averageScore ?? prev.last_score,
        best_score: averageScore != null ? Math.max(prev.best_score ?? 0, averageScore) : prev.best_score,
        sessions: prev.sessions + 1,
        last_session_scores: repetitionScores,
        score_history: scoreHistory,
      };
      await storage.setItem(PROGRESS_KEY(planId, exercise_id), JSON.stringify(updated));
    } catch {/* */}
  };

  const onMessage = async (e: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(e.nativeEvent.data);
      if (msg.type === "ready") setLoading(false);
      else if (msg.type === "rep_complete") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        const score = typeof msg.score === "number" ? msg.score : null;
        if (score != null) {
          scoresThisSession.current.push(score);
        }
        // Persist per-rep progress immediately so closing the screen mid-session
        // doesn't lose work.
        await saveRepProgress(1);
      } else if (msg.type === "exercise_complete") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        const arr = scoresThisSession.current;
        const avg = arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : null;
        setDoneInfo({ reps: msg.reps || 0, avgScore: avg });
        if (!isLibraryTest) {
          await saveSessionAverage(avg, [...arr]);
          try {
            await authedFetch("/api/alira/activities", {
              method: "POST",
              body: JSON.stringify({
                exercise_id: exercise_id || "",
                plan_id: planId,
                completed_reps: Number(msg.reps || arr.length || 0),
                average_score: avg,
                repetition_scores: arr,
                completed_at: new Date().toISOString(),
              }),
            });
          } catch {
            // Local exercise progress remains available and can sync on a later session.
          }
          try {
            // Earn today's check mark on the daily check-in calendar.
            await authedFetch("/api/users/daily-checkin/complete", {
              method: "POST",
              body: JSON.stringify({ date: localDateString() }),
            });
          } catch {
            // The calendar refreshes from the server on the next Home focus.
          }
        }
        setTimeout(() => router.back(), 2400);
      } else if (msg.type === "camera_error") {
        setError("Camera unavailable. Please grant camera permission in your phone settings and try again.");
      } else if (msg.type === "exit") {
        router.back();
      }
    } catch {/* */}
  };

  return (
    <View style={styles.container}>
      <WebView
        ref={webRef}
        testID="exercise-webview"
        source={{ uri: url }}
        style={styles.web}
        originWhitelist={["*"]}
        javaScriptEnabled
        domStorageEnabled
        mediaPlaybackRequiresUserAction={false}
        allowsInlineMediaPlayback
        {...(Platform.OS === "ios" ? { mediaCapturePermissionGrantType: "grant" as any } : {})}
        onPermissionRequest={(event: any) => { try { event?.grant(event?.resources || []); } catch {} }}
        onMessage={onMessage}
        onLoadEnd={() => setLoading(false)}
        onError={(e) => setError(String(e.nativeEvent.description || e.nativeEvent))}
      />
      {loading && (
        <View style={styles.overlay} pointerEvents="none">
          <ActivityIndicator size="large" color={colors.brandSecondary} />
          <Text style={styles.overlayText}>Preparing {name || "exercise"}…</Text>
        </View>
      )}
      {doneInfo && (
        <View style={styles.overlay} testID="exercise-done-overlay">
          <Ionicons name="checkmark-circle" size={56} color={colors.success} />
          <Text style={styles.doneTitle}>{isLibraryTest ? "Exercise test complete!" : "Exercise complete!"}</Text>
          {doneInfo.avgScore != null && (
            <Text style={styles.doneScore}>Session average: {doneInfo.avgScore}/100</Text>
          )}
          <Text style={styles.doneSub}>{isLibraryTest ? "Not saved to Progress. Returning to the library…" : "Returning to your plan…"}</Text>
        </View>
      )}
      {error && (
        <View style={styles.errorWrap} testID="exercise-error">
          <Ionicons name="alert-circle" size={42} color={colors.brandSecondary} />
          <Text style={styles.errorTitle}>{error}</Text>
          <Pressable onPress={() => router.back()} style={styles.errorBtn} testID="exercise-error-back">
            <Text style={styles.errorBtnText}>Go back</Text>
          </Pressable>
        </View>
      )}
      <SafetyStopStrip />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0c100e" },
  web: { flex: 1, backgroundColor: "#0c100e" },
  overlay: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", backgroundColor: "#0c100e", gap: spacing.md },
  overlayText: { color: colors.onSurfaceInverse, fontSize: 16, fontWeight: "600" },
  doneTitle: { color: colors.onSurfaceInverse, fontSize: 22, fontWeight: "800" },
  doneScore: { color: colors.brandSecondary, fontSize: 18, fontWeight: "700" },
  doneSub: { color: colors.onSurfaceTertiary, fontSize: 15 },
  errorWrap: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", padding: spacing.lg, gap: spacing.md, backgroundColor: "#0c100eEE" },
  errorTitle: { color: colors.onSurfaceInverse, fontSize: 16, textAlign: "center", lineHeight: 22 },
  errorBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.lg },
  errorBtnText: { color: "#fff", fontWeight: "700" },
});
