import { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Platform, Animated } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { PointsCelebration, PointsCelebrationEvent, celebrationEvent } from "@/src/components/PointsCelebration";
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
};

const PROGRESS_KEY = (planId: string, exId: string) => `ex_progress_v1:${planId}:${exId}`;

export default function ExerciseScreen() {
  const router = useRouter();
  const { exercise_id, name, plan_id, sets, reps, library_test } = useLocalSearchParams<{ exercise_id: string; name?: string; plan_id?: string; sets?: string; reps?: string; library_test?: string }>();
  const webRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [celebration, setCelebration] = useState<PointsCelebrationEvent | null>(null);
  const [doneInfo, setDoneInfo] = useState<{ reps: number; avgScore: number | null } | null>(null);
  const [voiceGuidance, setVoiceGuidance] = useState(true);
  // Per-rep toast state
  const [repToast, setRepToast] = useState<{ rep: number; total: number; score: number } | null>(null);
  const toastOpacity = useRef(new Animated.Value(0)).current;
  const scoresThisSession = useRef<number[]>([]);

  const totalSets = parseInt(sets || "3", 10);
  const totalReps = parseInt(reps || "10", 10);
  const totalAll = totalSets * totalReps;
  const planId = plan_id || "default";
  const isLibraryTest = library_test === "1";

  const guidedReps = Math.max(1, Math.min(20, totalReps));
  const url = `${BASE}/api/rehab/runner?exercise_id=${encodeURIComponent(exercise_id || "ex_maintenance")}&reps=${guidedReps}&voice_guidance=${voiceGuidance ? "1" : "0"}`;

  useEffect(() => {
    void loadUserPreferences().then((saved) => setVoiceGuidance(saved.voiceGuidance));
  }, []);

  const showRepToast = (rep: number, total: number, score: number) => {
    setRepToast({ rep, total, score });
    Animated.sequence([
      Animated.timing(toastOpacity, { toValue: 1, duration: 220, useNativeDriver: true }),
      Animated.delay(2200),
      Animated.timing(toastOpacity, { toValue: 0, duration: 320, useNativeDriver: true }),
    ]).start(() => setRepToast(null));
  };

  const saveProgress = async (newReps: number, score: number | null) => {
    if (isLibraryTest) return;
    if (!exercise_id) return;
    try {
      const raw = await storage.getItem(PROGRESS_KEY(planId, exercise_id));
      const prev: ExerciseProgress = raw
        ? JSON.parse(raw)
        : { completed_reps: 0, total_reps: totalAll, last_score: null, best_score: null, sessions: 0 };
      const updated: ExerciseProgress = {
        completed_reps: Math.min(totalAll, prev.completed_reps + newReps),
        total_reps: totalAll,
        last_score: score != null ? score : prev.last_score,
        best_score: score != null ? Math.max(prev.best_score ?? 0, score) : prev.best_score,
        sessions: prev.sessions + (newReps > 0 ? 0 : 0),
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
          showRepToast(msg.rep, msg.total, score);
        }
        // Persist per-rep progress immediately so closing the screen mid-session
        // doesn't lose work.
        await saveProgress(1, score);
      } else if (msg.type === "exercise_complete") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        const arr = scoresThisSession.current;
        const avg = arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : null;
        setDoneInfo({ reps: msg.reps || 0, avgScore: avg });
        if (!isLibraryTest) {
          // Mark this session complete — bump sessions counter
          try {
            const raw = await storage.getItem(PROGRESS_KEY(planId, exercise_id || ""));
            if (raw) {
              const p: ExerciseProgress = JSON.parse(raw);
              p.sessions += 1;
              await storage.setItem(PROGRESS_KEY(planId, exercise_id || ""), JSON.stringify(p));
            }
          } catch {/* */}
          try {
            await authedFetch("/api/alira/activities", {
              method: "POST",
              body: JSON.stringify({
                exercise_id: exercise_id || "",
                plan_id: planId,
                completed_reps: Number(msg.reps || arr.length || 0),
                average_score: avg,
                completed_at: new Date().toISOString(),
              }),
            });
            // Every completed exercise earns points - celebrate, then fade out.
            setCelebration(celebrationEvent(5, "Exercise complete - great work!"));
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
      {repToast && (
        <Animated.View style={[styles.repToast, { opacity: toastOpacity }]} testID="rep-score-toast" pointerEvents="none">
          <View style={styles.repToastInner}>
            <Text style={styles.repToastRep}>Rep {repToast.rep} / {repToast.total}</Text>
            <Text style={styles.repToastScore}>{repToast.score}<Text style={styles.repToastSlash}>/100</Text></Text>
            <Text style={styles.repToastLabel}>{labelFor(repToast.score)}</Text>
          </View>
        </Animated.View>
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
      <PointsCelebration event={celebration} onDone={() => setCelebration(null)} />
    </View>
  );
}

function labelFor(s: number): string {
  if (s >= 90) return "Excellent form";
  if (s >= 75) return "Great work";
  if (s >= 60) return "Good effort";
  if (s >= 45) return "Keep practicing";
  return "Take it gently";
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0c100e" },
  web: { flex: 1, backgroundColor: "#0c100e" },
  overlay: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", backgroundColor: "#0c100e", gap: spacing.md },
  overlayText: { color: colors.onSurfaceInverse, fontSize: 16, fontWeight: "600" },
  doneTitle: { color: colors.onSurfaceInverse, fontSize: 22, fontWeight: "800" },
  doneScore: { color: colors.brandSecondary, fontSize: 18, fontWeight: "700" },
  doneSub: { color: colors.onSurfaceTertiary, fontSize: 15 },
  // Per-rep score toast
  repToast: { position: "absolute", top: "30%", left: 0, right: 0, alignItems: "center", pointerEvents: "none" },
  repToastInner: { backgroundColor: "rgba(28,32,29,0.92)", borderRadius: radius.lg, paddingHorizontal: 28, paddingVertical: 18, alignItems: "center", gap: 4, minWidth: 200 },
  repToastRep: { color: "#D9E5DC", fontSize: 13, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase" },
  repToastScore: { color: "#fff", fontSize: 44, fontWeight: "800" },
  repToastSlash: { color: "#D9E5DC", fontSize: 18, fontWeight: "600" },
  repToastLabel: { color: "#7FE5A3", fontSize: 15, fontWeight: "700" },
  errorWrap: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", padding: spacing.lg, gap: spacing.md, backgroundColor: "#0c100eEE" },
  errorTitle: { color: colors.onSurfaceInverse, fontSize: 16, textAlign: "center", lineHeight: 22 },
  errorBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.lg },
  errorBtnText: { color: "#fff", fontWeight: "700" },
});
