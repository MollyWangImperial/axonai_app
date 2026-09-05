import { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Platform } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { storage } from "@/src/utils/storage";
import { SafetyStopStrip } from "@/src/components/SafetyStopStrip";
import { appNow, loadAppDateOverride } from "@/src/appDate";
import { localDateString } from "@/src/components/DailyCheckInCalendar";
import { API_BASE as BASE } from "@/src/config";
import { loadUserPreferences } from "@/src/userPreferences";
import { getUserId } from "@/src/auth";
import { exerciseProgressKey, flushPatientActivities, queuePatientActivity } from "@/src/patientActivitySync";

type ExerciseProgress = {
  completed_reps: number;
  total_reps: number;
  last_score: number | null;
  best_score: number | null;
  sessions: number;
  last_session_scores?: number[];
  score_history?: { completed_at: string; average_score: number; repetition_scores: number[] }[];
  day?: string;
};

export default function ExerciseScreen() {
  const router = useRouter();
  const { exercise_id, name, plan_id, sets, reps, difficulty, variation, affected_side, rehab_session_id, library_test } = useLocalSearchParams<{ exercise_id: string; name?: string; plan_id?: string; sets?: string; reps?: string; difficulty?: string; variation?: string; affected_side?: string; rehab_session_id?: string; library_test?: string }>();
  const webRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [doneInfo, setDoneInfo] = useState<{ reps: number; avgScore: number | null } | null>(null);
  const [voiceGuidance, setVoiceGuidance] = useState(true);
  const scoresThisSession = useRef<number[]>([]);
  const [account] = useState(() => getUserId());
  const [attemptId] = useState(() => `exercise-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  const seenReps = useRef(new Set<number>());
  const messages = useRef<Promise<void>>(Promise.resolve());
  const [syncMessage, setSyncMessage] = useState("");

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
    void loadAppDateOverride();
    void loadUserPreferences().then((saved) => setVoiceGuidance(saved.voiceGuidance));
  }, []);

  const saveRepProgress = async (rep: number, score: number | null, pointEarned: boolean) => {
    if (isLibraryTest) return;
    if (!exercise_id) return;
    const userId = await account;
    if (!userId) throw new Error("Sign in to save your repetitions.");
    const today = localDateString();
    await queuePatientActivity(userId, {
      id: `${attemptId}:rep:${rep}`, path: "/api/users/exercise-repetitions",
      body: { exercise_id, plan_id: planId, session_id: attemptId, day: today, rep, total_reps: totalAll, score, point_earned: pointEarned },
    });
    void flushPatientActivities().then((saved) => setSyncMessage(saved ? "" : "Saved on this device. Waiting to sync to your account."));
    try {
      const raw = await storage.getItem(exerciseProgressKey(userId, planId, exercise_id), "");
      const prev: ExerciseProgress = raw
        ? JSON.parse(raw)
        : { completed_reps: 0, total_reps: totalAll, last_score: null, best_score: null, sessions: 0 };
      // Today's plan starts from zero each day: repetitions from an earlier
      // day are not carried into today's count (the score history is kept).
      const completedToday = prev.day === today ? prev.completed_reps : 0;
      const updated: ExerciseProgress = {
        completed_reps: Math.min(totalAll, completedToday + 1),
        total_reps: totalAll,
        last_score: prev.last_score,
        best_score: prev.best_score,
        sessions: prev.sessions,
        last_session_scores: prev.last_session_scores,
        score_history: prev.score_history,
        day: today,
      };
      await storage.setItem(exerciseProgressKey(userId, planId, exercise_id), JSON.stringify(updated));
    } catch {/* */}
  };

  const saveSessionAverage = async (averageScore: number | null, repetitionScores: number[]) => {
    if (isLibraryTest || !exercise_id) return;
    const userId = await account;
    if (!userId) return;
    try {
      const raw = await storage.getItem(exerciseProgressKey(userId, planId, exercise_id), "");
      const prev: ExerciseProgress = raw
        ? JSON.parse(raw)
        : { completed_reps: 0, total_reps: totalAll, last_score: null, best_score: null, sessions: 0 };
      const completedAt = appNow().toISOString();
      const scoreHistory = averageScore == null
        ? prev.score_history || []
        : [
            ...(prev.score_history || []),
            { completed_at: completedAt, average_score: averageScore, repetition_scores: repetitionScores },
          ].slice(-60);
      const updated: ExerciseProgress = {
        ...prev,
        day: localDateString(),
        completed_reps: prev.day === localDateString() ? prev.completed_reps : 0,
        total_reps: totalAll,
        last_score: averageScore ?? prev.last_score,
        best_score: averageScore != null ? Math.max(prev.best_score ?? 0, averageScore) : prev.best_score,
        sessions: prev.sessions + 1,
        last_session_scores: repetitionScores,
        score_history: scoreHistory,
      };
      await storage.setItem(exerciseProgressKey(userId, planId, exercise_id), JSON.stringify(updated));
    } catch {/* */}
  };

  const handleMessage = async (e: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(e.nativeEvent.data);
      if (msg.type === "ready") setLoading(false);
      else if (msg.type === "rep_complete") {
        const rep = Number(msg.rep);
        if (!Number.isInteger(rep) || rep < 1 || seenReps.current.has(rep)) return;
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        const score = typeof msg.score === "number" ? msg.score : null;
        await saveRepProgress(rep, score, msg.point_earned === true);
        seenReps.current.add(rep);
        if (score != null) {
          scoresThisSession.current.push(score);
        }
      } else if (msg.type === "exercise_complete") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        const arr = scoresThisSession.current;
        const rawAvg = arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : null;
        // The runner asks after the last repetition whether a carer or family
        // member helped. An assisted session still counts, but scores are
        // halved (the server applies the same factor to what it stores, so we
        // send the RAW scores plus the flag - never pre-halved).
        const assisted = msg.assisted === true;
        const avg = assisted && rawAvg != null ? Math.round(rawAvg / 2) : rawAvg;
        const localScores = assisted ? arr.map((s) => Math.round(s / 2)) : [...arr];
        setDoneInfo({ reps: msg.reps || 0, avgScore: avg });
        if (!isLibraryTest) {
          const userId = await account;
          if (!userId) throw new Error("Sign in to save your exercise.");
          await saveSessionAverage(avg, localScores);
          await queuePatientActivity(userId, {
              id: `${attemptId}:complete`, path: "/api/alira/activities",
              body: {
                client_activity_id: attemptId,
                day: localDateString(),
                exercise_id: exercise_id || "",
                plan_id: planId,
                completed_reps: Number(msg.reps || arr.length || 0),
                // Only correctly performed repetitions earn points (the runner
                // counts them: no compensation, score at or above the threshold).
                quality_reps: typeof msg.quality_reps === "number" ? msg.quality_reps : undefined,
                average_score: rawAvg,
                repetition_scores: arr,
                assisted,
                completed_at: appNow().toISOString(),
              },
            });
          await queuePatientActivity(userId, {
              id: `${attemptId}:checkin`, path: "/api/users/daily-checkin/complete",
              body: { date: localDateString() },
            });
          void flushPatientActivities().then((saved) => setSyncMessage(saved ? "Saved to your account." : "Saved on this device. Waiting to sync to your account."));
        }
        setTimeout(() => router.back(), 2400);
      } else if (msg.type === "camera_error") {
        setError("Camera unavailable. Please grant camera permission in your phone settings and try again.");
      } else if (msg.type === "exit") {
        router.back();
      }
    } catch (error) {
      setSyncMessage(error instanceof Error ? error.message : "Activity could not be saved. Please retry.");
    }
  };

  const onMessage = (event: WebViewMessageEvent) => {
    messages.current = messages.current.then(() => handleMessage(event));
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
      {!!syncMessage && <Text accessibilityLiveRegion="polite" style={{ color: "#fff", backgroundColor: "#254c3e", padding: spacing.sm }}>{syncMessage}</Text>}
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
