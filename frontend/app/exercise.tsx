import { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Platform, Animated } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { storage } from "@/src/utils/storage";
import { API_BASE as BASE } from "@/src/config";
import { loadUserPreferences } from "@/src/userPreferences";

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
  const { exercise_id, name, plan_id, sets, reps } = useLocalSearchParams<{ exercise_id: string; name?: string; plan_id?: string; sets?: string; reps?: string }>();
  const webRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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
    if (!exercise_id) return;
    try {
      const raw = await storage.getItem<string>(PROGRESS_KEY(planId, exercise_id), "");
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
        // Mark this session complete — bump sessions counter
        try {
          const raw = await storage.getItem<string>(PROGRESS_KEY(planId, exercise_id || ""), "");
          if (raw) {
            const p: ExerciseProgress = JSON.parse(raw);
            p.sessions += 1;
            await storage.setItem(PROGRESS_KEY(planId, exercise_id || ""), JSON.stringify(p));
          }
        } catch {/* */}
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
        {...({ onPermissionRequest: (event: any) => { try { event?.grant(event?.resources || []); } catch {} } } as any)}
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
          <Text style={styles.doneTitle}>Exercise complete!</Text>
          {doneInfo.avgScore != null && (
            <Text style={styles.doneScore}>Session average: {doneInfo.avgScore}/100</Text>
          )}
          <Text style={styles.doneSub}>Returning to your plan…</Text>
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
  overlayText: { color: colors.onSurfaceInverse, fontSize: 18, lineHeight: 25, fontWeight: "600" },
  doneTitle: { color: colors.onSurfaceInverse, fontSize: 26, lineHeight: 33, fontWeight: "800" },
  doneScore: { color: "#D59B80", fontSize: 20, lineHeight: 27, fontWeight: "700" },
  doneSub: { color: "#D4DED5", fontSize: 16, lineHeight: 23 },
  // Per-rep score toast
  repToast: { position: "absolute", top: "30%", left: 0, right: 0, alignItems: "center", pointerEvents: "none" },
  repToastInner: { backgroundColor: "rgba(27, 49, 38, 0.96)", borderRadius: radius.lg, borderWidth: 1, borderColor: "rgba(227, 230, 222, 0.28)", paddingHorizontal: 30, paddingVertical: 20, alignItems: "center", gap: 5, minWidth: 220 },
  repToastRep: { color: "#E4ECE2", fontSize: 16, fontWeight: "700", letterSpacing: 0.7, textTransform: "uppercase" },
  repToastScore: { color: "#FFFEFA", fontSize: 48, lineHeight: 54, fontWeight: "800" },
  repToastSlash: { color: "#E4ECE2", fontSize: 20, fontWeight: "600" },
  repToastLabel: { color: "#B7E8C5", fontSize: 16, lineHeight: 22, fontWeight: "700" },
  errorWrap: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", padding: spacing.lg, gap: spacing.md, backgroundColor: "#0c100eEE" },
  errorTitle: { color: colors.onSurfaceInverse, fontSize: 17, textAlign: "center", lineHeight: 25 },
  errorBtn: { minHeight: 52, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  errorBtnText: { color: colors.onBrandPrimary, fontSize: 16, fontWeight: "700" },
});
