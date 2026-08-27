import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { fetchAssessment, Assessment } from "@/src/api";
import { storage } from "@/src/utils/storage";
import { authedFetch } from "@/src/auth";
import PaywallModal from "@/src/components/PaywallModal";

type ExerciseProgress = {
  completed_reps: number;
  total_reps: number;
  last_score: number | null;   // 0-100, average of last session
  best_score: number | null;
  sessions: number;
};

const PROGRESS_KEY = (planId: string, exId: string) => `ex_progress_v1:${planId}:${exId}`;

export default function RehabPlanScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState<Record<string, ExerciseProgress>>({});
  const [paywallOpen, setPaywallOpen] = useState(false);
  const [paywallReason, setPaywallReason] = useState<string | undefined>();

  const planId = id || "default";

  const loadProgress = React.useCallback(async (plan: Assessment) => {
    const out: Record<string, ExerciseProgress> = {};
    for (const ex of plan.rehab_plan) {
      try {
        const raw = await storage.getItem(PROGRESS_KEY(planId, ex.id));
        if (raw) out[ex.id] = JSON.parse(raw);
        else out[ex.id] = { completed_reps: 0, total_reps: ex.sets * ex.reps, last_score: null, best_score: null, sessions: 0 };
      } catch {
        out[ex.id] = { completed_reps: 0, total_reps: ex.sets * ex.reps, last_score: null, best_score: null, sessions: 0 };
      }
    }
    setProgress(out);
  }, [planId]);

  useEffect(() => {
    (async () => {
      try {
        if (id) {
          const a = await fetchAssessment(id);
          setData(a);
          await loadProgress(a);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [id, loadProgress]);

  // Reload progress whenever the screen comes back into focus (after exercise returns)
  useFocusEffect(
    React.useCallback(() => {
      if (data) loadProgress(data);
    }, [data, loadProgress])
  );

  const completedCount = Object.values(progress).filter((p) => p.completed_reps >= p.total_reps).length;

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }
  if (!data) {
    return (
      <View style={[styles.container, styles.center]}>
        <Text>No plan available.</Text>
      </View>
    );
  }

  if (data.clinical_review_gate?.rehab_access !== "allowed" || data.rehab_plan.length === 0) {
    const gate = data.clinical_review_gate;
    const awaiting = gate?.status === "awaiting_model_analysis";
    const noRehabNeeded = gate?.status === "no_rehab_needed" || gate?.rehab_access === "not_needed";
    const title = gate?.patient_title || "No rehabilitation plan is available";
    const message = gate?.patient_message || "This assessment did not produce exercises for automatic recommendation.";
    const nextStep = gate?.next_step || "Return home and review the result with your therapist if you still have symptoms.";
    return (
      <View style={styles.container}>
        <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
          <Pressable onPress={() => router.replace("/")} style={styles.backBtn} testID="plan-blocked-back">
            <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.headerTitle}>Rehab Plan</Text>
          <View style={{ width: 40 }} />
        </View>
        <View style={[styles.center, styles.blockedContent]} testID={noRehabNeeded ? "plan-no-rehab-needed" : "plan-clinical-review-hold"}>
          <View style={styles.blockedIcon}>
            <Ionicons name={noRehabNeeded ? "checkmark-circle-outline" : awaiting ? "hourglass-outline" : "people-outline"} size={30} color={colors.brandPrimary} />
          </View>
          <Text style={styles.blockedTitle}>{title}</Text>
          <Text style={styles.blockedText}>{message}</Text>
          <Text style={styles.blockedNext}>{nextStep}</Text>
          <Pressable onPress={() => router.replace("/")} style={styles.blockedButton} testID="plan-blocked-home">
            <Ionicons name="home-outline" size={20} color={colors.onBrandPrimary} />
            <Text style={styles.guidedBtnText}>Return Home</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="plan-back">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Rehab Plan</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 }}>
        <View style={styles.hero}>
          <Text style={styles.heroTitle}>Today&apos;s Plan</Text>
          <Text style={styles.heroSub}>
            {data.rehab_plan.length} exercises tailored to your focus areas. Evidence-based protocols.
          </Text>
          <View style={styles.progress}>
            <View style={[styles.progressFill, { width: `${(completedCount / Math.max(1, data.rehab_plan.length)) * 100}%` }]} />
          </View>
          <Text style={styles.progressText}>{completedCount} of {data.rehab_plan.length} complete</Text>
        </View>

        {data.rehab_plan.map((ex, i) => {
          const p = progress[ex.id] || { completed_reps: 0, total_reps: ex.sets * ex.reps, last_score: null, best_score: null, sessions: 0 };
          const pct = Math.round((p.completed_reps / Math.max(1, p.total_reps)) * 100);
          const isDone = pct >= 100;
          return (
            <View
              key={ex.id}
              style={[styles.exCard, isDone && styles.exCardDone]}
              testID={`exercise-${ex.id}`}
            >
              <View style={styles.exHead}>
                <View style={[styles.exNum, isDone && { backgroundColor: colors.success }]}>
                  {isDone ? (
                    <Ionicons name="checkmark" size={20} color="#fff" />
                  ) : (
                    <Text style={styles.exNumText}>{i + 1}</Text>
                  )}
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.exTitle}>{ex.name}</Text>
                  <Text style={styles.exMeta}>{ex.sets} sets × {ex.reps} reps · {ex.frequency}</Text>
                </View>
                <View style={styles.pctBadge} testID={`exercise-progress-${ex.id}`}>
                  <Text style={styles.pctBadgeText}>{pct}%</Text>
                </View>
              </View>

              <View style={styles.progressMini}>
                <View style={[styles.progressMiniFill, { width: `${pct}%` }, isDone && { backgroundColor: colors.success }]} />
              </View>
              {p.last_score != null && (
                <Text style={styles.scoreLine} testID={`exercise-score-${ex.id}`}>
                  ⭐ Last session score: {p.last_score}/100{p.best_score != null && p.best_score > p.last_score ? ` · Best ${p.best_score}` : ""}
                </Text>
              )}

              <Text style={styles.exDesc}>{ex.description}</Text>
              {!!ex.selection_reason && <Text style={styles.exSource}>Reason: {ex.selection_reason}</Text>}
              {!!ex.safety_note && <Text style={styles.safetyNote}>{ex.safety_note}</Text>}
              <Text style={styles.exSource}>📖 {ex.source}</Text>
              <View style={styles.exActions}>
                <Pressable
                  onPress={async () => {
                    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                    // Credit pre-flight: skip if subscription_active, else require >=30.
                    try {
                      const r = await authedFetch("/api/credits/balance");
                      const b = await r.json();
                      const needed = (b.costs?.guided_exercise ?? 30);
                      if (!b.subscription_active && (b.credits ?? 0) < needed) {
                        setPaywallReason("You're out of credits. Subscribe to unlock unlimited guided exercises.");
                        setPaywallOpen(true);
                        return;
                      }
                    } catch {/* offline — let backend gate later */}
                    router.push({ pathname: "/exercise", params: { exercise_id: ex.id, name: ex.name, plan_id: planId, sets: String(ex.sets), reps: String(ex.reps) } });
                  }}
                  style={styles.guidedBtn}
                  testID={`exercise-guided-${ex.id}`}
                >
                  <Ionicons name="play" size={18} color="#fff" />
                  <Text style={styles.guidedBtnText}>{isDone ? "Practice again" : pct > 0 ? "Continue exercise" : "Start exercise"}</Text>
                </Pressable>
              </View>
            </View>
          );
        })}

        <Text style={styles.disclaimer}>
          This plan is an educational guide derived from established rehabilitation sources. Always consult your therapist or clinician before starting a new exercise program.
        </Text>
      </ScrollView>

      <View style={[styles.ctaBar, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Pressable
          onPress={() => router.replace("/")}
          style={styles.cta}
          testID="plan-done"
        >
          <Ionicons name="checkmark-circle" size={22} color={colors.onBrandPrimary} />
          <Text style={styles.ctaText}>Finish Session</Text>
        </Pressable>
      </View>

      <PaywallModal
        visible={paywallOpen}
        onClose={() => setPaywallOpen(false)}
        onSubscribed={() => { /* balance auto-refreshes on next focus */ }}
        reason={paywallReason}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  blockedContent: { flex: 1, padding: spacing.xl },
  blockedIcon: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary, marginBottom: spacing.md },
  blockedTitle: { fontSize: 22, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginBottom: spacing.sm },
  blockedText: { fontSize: 15, lineHeight: 22, color: colors.onSurfaceSecondary, textAlign: "center" },
  blockedNext: { fontSize: 15, lineHeight: 22, fontWeight: "700", color: colors.onSurface, textAlign: "center", marginTop: spacing.md },
  blockedButton: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, alignItems: "center", marginTop: spacing.xl },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  hero: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, gap: spacing.sm },
  heroTitle: { fontSize: 22, fontWeight: "800", color: colors.onBrandTertiary },
  heroSub: { color: colors.onBrandTertiary, fontSize: 14, lineHeight: 20 },
  progress: { height: 8, backgroundColor: "rgba(28,32,29,0.15)", borderRadius: 4, marginTop: spacing.sm, overflow: "hidden" },
  progressFill: { height: "100%", backgroundColor: colors.brandPrimary },
  progressText: { color: colors.onBrandTertiary, fontSize: 13, fontWeight: "600" },
  exCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.sm, gap: spacing.sm, borderWidth: 2, borderColor: "transparent" },
  exCardDone: { borderColor: colors.success, backgroundColor: "#EAF3EE" },
  exHead: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  exNum: { width: 36, height: 36, borderRadius: 10, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  exNumText: { color: "#fff", fontSize: 16, fontWeight: "800" },
  exTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface, marginBottom: 2 },
  exMeta: { fontSize: 13, color: colors.brandPrimary, fontWeight: "600" },
  pctBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: colors.brandTertiary, minWidth: 50, alignItems: "center" },
  pctBadgeText: { fontSize: 12, fontWeight: "800", color: colors.onBrandTertiary },
  progressMini: { height: 6, backgroundColor: "rgba(28,32,29,0.12)", borderRadius: 3, overflow: "hidden" },
  progressMiniFill: { height: "100%", backgroundColor: colors.brandPrimary, borderRadius: 3 },
  scoreLine: { fontSize: 12, color: colors.brandPrimary, fontWeight: "700" },
  exDesc: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20 },
  exSource: { fontSize: 12, color: colors.onSurfaceTertiary, fontStyle: "italic" },
  safetyNote: { fontSize: 12, color: colors.warning, lineHeight: 18 },
  exActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  guidedBtn: { flex: 1, flexDirection: "row", gap: 6, backgroundColor: colors.brandPrimary, paddingVertical: 12, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  guidedBtnText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  disclaimer: { fontSize: 12, color: colors.onSurfaceTertiary, fontStyle: "italic", marginTop: spacing.lg, lineHeight: 18 },
  ctaBar: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider },
  cta: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: spacing.md, alignItems: "center", justifyContent: "center", minHeight: 56 },
  ctaText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "700" },
});
