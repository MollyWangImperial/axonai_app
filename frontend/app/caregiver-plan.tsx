import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

import { authedFetch } from "@/src/auth";
import { localDateString } from "@/src/components/DailyCheckInCalendar";
import { PointsCelebration, PointsCelebrationEvent, celebrationEvent } from "@/src/components/PointsCelebration";
import { SafetyStopStrip } from "@/src/components/SafetyStopStrip";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import { colors, radius, spacing } from "@/src/theme";

// When no camera assessment is possible, recovery starts here: qualitative,
// caregiver-delivered routines (gentle strengthening and relaxation of the
// affected muscle groups from approved guidance). The carer ticks each routine
// off once it is done today; completing them all earns the day's check mark.

type CaregiverProgramme = {
  id: string;
  domain: string;
  goal: string;
  muscle_groups: string[];
  instructions: string[];
  dose: string;
  safety_limits: string;
};

type CaregiverProgress = {
  mode: string;
  session_days_this_week: number;
  session_days_prior_week: number;
  total_sessions: number;
  movement_emerging: boolean;
  re_screen_suggested: boolean;
  message: string;
};

type CaregiverPlan = {
  applicable: boolean;
  audience: string;
  programmes: CaregiverProgramme[];
  stop_and_call?: string;
  daily_delivery?: {
    required_today: boolean;
    checkoff_instruction?: string;
    programme_ids: string[];
    completed_today_ids: string[];
    remaining_today_ids: string[];
    completed_today: boolean;
  };
  progress?: CaregiverProgress;
};

// The carer's observation of how much the patient joined in - recorded with
// every delivered routine, this is how non-camera patients show progress.
const OBSERVATION_OPTIONS = [
  { value: "none", label: "No movement yet" },
  { value: "flicker", label: "A flicker of effort" },
  { value: "small_movement", label: "Small movements" },
  { value: "more_than_before", label: "Joining in more than before" },
] as const;

const DOMAIN_LABELS: Record<string, string> = {
  upper_limb: "Arm",
  hand: "Hand",
  lower_limb: "Leg",
};

const CACHE_KEY = "caregiver-plan";

export default function CaregiverPlanScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const cached = getScreenCache<CaregiverPlan>(CACHE_KEY);
  const [plan, setPlan] = useState<CaregiverPlan | null>(cached ?? null);
  const [doneIds, setDoneIds] = useState<string[]>(cached?.daily_delivery?.completed_today_ids ?? []);
  const [loading, setLoading] = useState(!cached);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [observingId, setObservingId] = useState<string | null>(null);
  const [celebration, setCelebration] = useState<PointsCelebrationEvent | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await authedFetch("/api/alira/care-plan");
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Could not load the caregiver programme.");
      const caregiverPlan = body?.caregiver_plan as CaregiverPlan | undefined;
      if (caregiverPlan) {
        setPlan(caregiverPlan);
        setDoneIds(caregiverPlan.daily_delivery?.completed_today_ids ?? []);
        setScreenCache<CaregiverPlan>(CACHE_KEY, caregiverPlan);
        setError(null);
      }
    } catch (e: any) {
      if (!plan) setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }, [plan]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const markDone = async (programmeId: string, observedResponse: string) => {
    if (doneIds.includes(programmeId) || saving) return;
    setSaving(programmeId);
    try {
      const response = await authedFetch("/api/alira/activities", {
        method: "POST",
        body: JSON.stringify({
          exercise_id: programmeId,
          plan_id: "caregiver",
          completed_reps: 1,
          observed_response: observedResponse,
          completed_at: new Date().toISOString(),
        }),
      });
      if (!response.ok) throw new Error("Could not save the routine as done.");
      const nextDone = [...doneIds, programmeId];
      setDoneIds(nextDone);
      setObservingId(null);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      // Each delivered routine earns points - celebrate, then fade out.
      setCelebration(celebrationEvent(5, "Routine delivered - thank you!"));
      const allIds = plan?.daily_delivery?.programme_ids ?? plan?.programmes.map((item) => item.id) ?? [];
      if (allIds.length > 0 && allIds.every((id) => nextDone.includes(id))) {
        // Every routine is delivered: the day earns its calendar check mark.
        await authedFetch("/api/users/daily-checkin/complete", {
          method: "POST",
          body: JSON.stringify({ date: localDateString() }),
        }).catch(() => null);
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setSaving(null);
    }
  };

  const allDone = Boolean(
    plan?.programmes?.length && plan.programmes.every((item) => doneIds.includes(item.id)),
  );

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="caregiver-plan-back">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Caregiver programme</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>{"Today's caregiver-delivered exercises"}</Text>
        <Text style={styles.sub}>
          These routines are for the carer to deliver: gentle strengthening of weak muscle groups and
          relaxation of tight ones, following approved guidance. Move slowly, never into pain, and tick
          each routine once it is done today.
        </Text>

        {loading && !plan && <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.lg }} />}
        {error && <Text style={styles.errorText}>{error}</Text>}

        {plan?.progress ? (
          <View style={styles.progressCard} testID="caregiver-plan-progress">
            <Text style={styles.progressTitle}>Progress</Text>
            <View style={styles.progressStatsRow}>
              <View style={styles.progressStat}>
                <Text style={styles.progressStatNumber}>{plan.progress.session_days_this_week}</Text>
                <Text style={styles.progressStatLabel}>session days this week</Text>
              </View>
              <View style={styles.progressStat}>
                <Text style={styles.progressStatNumber}>{plan.progress.session_days_prior_week}</Text>
                <Text style={styles.progressStatLabel}>last week</Text>
              </View>
              <View style={styles.progressStat}>
                <Text style={styles.progressStatNumber}>{plan.progress.total_sessions}</Text>
                <Text style={styles.progressStatLabel}>total routines</Text>
              </View>
            </View>
            <Text style={styles.progressMessage}>{plan.progress.message}</Text>
            {plan.progress.re_screen_suggested && (
              <Pressable
                testID="caregiver-plan-rescreen"
                onPress={() => router.push("/onboarding?mode=assessment-readiness" as never)}
                style={styles.rescreenBtn}
              >
                <Ionicons name="trending-up" size={18} color={colors.onBrandPrimary} />
                <Text style={styles.rescreenBtnText}>Update readiness answers</Text>
              </Pressable>
            )}
          </View>
        ) : null}

        {plan?.stop_and_call ? (
          <View style={styles.stopCard} testID="caregiver-plan-stop-rules">
            <Ionicons name="alert-circle" size={20} color={colors.error} />
            <Text style={styles.stopText}>{plan.stop_and_call}</Text>
          </View>
        ) : null}

        {allDone && (
          <View style={styles.doneBanner} testID="caregiver-plan-all-done">
            <Ionicons name="checkmark-circle" size={22} color={colors.success} />
            <Text style={styles.doneBannerText}>
              Every routine is done for today - the calendar check mark is earned. Rest now; the next
              session is tomorrow.
            </Text>
          </View>
        )}

        {plan?.programmes?.map((programme) => {
          const done = doneIds.includes(programme.id);
          return (
            <View key={programme.id} style={styles.card} testID={`caregiver-programme-${programme.id}`}>
              <View style={styles.cardTop}>
                <Text style={styles.domain}>{DOMAIN_LABELS[programme.domain] || programme.domain}</Text>
                {done && <Ionicons name="checkmark-circle" size={20} color={colors.success} />}
              </View>
              <Text style={styles.goal}>{programme.goal}</Text>
              <Text style={styles.muscles}>Muscle groups: {programme.muscle_groups.join(", ")}</Text>
              {programme.instructions.map((step, index) => (
                <View key={step} style={styles.stepRow}>
                  <Text style={styles.stepNumber}>{index + 1}</Text>
                  <Text style={styles.stepText}>{step}</Text>
                </View>
              ))}
              <Text style={styles.dose}>{programme.dose}</Text>
              <Text style={styles.safety}>{programme.safety_limits}</Text>
              {observingId === programme.id && !done ? (
                <View style={styles.observationBlock} testID={`caregiver-observation-${programme.id}`}>
                  <Text style={styles.observationQuestion}>
                    During this routine, how much did the patient join in?
                  </Text>
                  {OBSERVATION_OPTIONS.map((option) => (
                    <Pressable
                      key={option.value}
                      testID={`caregiver-observation-${programme.id}-${option.value}`}
                      disabled={saving === programme.id}
                      onPress={() => markDone(programme.id, option.value)}
                      style={styles.observationOption}
                    >
                      <Ionicons name="radio-button-off" size={16} color={colors.brandPrimary} />
                      <Text style={styles.observationOptionText}>{option.label}</Text>
                    </Pressable>
                  ))}
                  {saving === programme.id && <ActivityIndicator color={colors.brandPrimary} size="small" />}
                </View>
              ) : (
                <Pressable
                  testID={`caregiver-programme-done-${programme.id}`}
                  disabled={done || saving === programme.id}
                  onPress={() => setObservingId(programme.id)}
                  style={[styles.doneBtn, done && styles.doneBtnDone]}
                >
                  <Ionicons name={done ? "checkmark-done" : "checkbox-outline"} size={18} color={done ? colors.success : colors.onBrandPrimary} />
                  <Text style={[styles.doneBtnText, done && styles.doneBtnTextDone]}>
                    {done ? "Done today" : "Mark as done today"}
                  </Text>
                </Pressable>
              )}
            </View>
          );
        })}

        {!loading && plan && plan.programmes.length === 0 && (
          <Text style={styles.errorText}>No caregiver routines are assigned right now.</Text>
        )}

        <SafetyStopStrip />
      </ScrollView>
      <PointsCelebration event={celebration} onDone={() => setCelebration(null)} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  scroll: { width: "100%", maxWidth: 620, alignSelf: "center", padding: spacing.lg, paddingBottom: 60 },
  title: { fontSize: 26, lineHeight: 32, fontWeight: "800", color: colors.onSurface },
  sub: { fontSize: 15, lineHeight: 22, color: colors.onSurfaceSecondary, marginTop: spacing.sm, marginBottom: spacing.md },
  progressCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.md, gap: spacing.sm },
  progressTitle: { fontSize: 16, fontWeight: "800", color: colors.onBrandTertiary },
  progressStatsRow: { flexDirection: "row", gap: spacing.md },
  progressStat: { flex: 1, alignItems: "center" },
  progressStatNumber: { fontSize: 24, fontWeight: "800", color: colors.onBrandTertiary },
  progressStatLabel: { fontSize: 11, lineHeight: 15, color: colors.onBrandTertiary, textAlign: "center" },
  progressMessage: { fontSize: 13, lineHeight: 19, color: colors.onBrandTertiary, fontWeight: "600" },
  rescreenBtn: { minHeight: 44, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  rescreenBtnText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "800" },
  observationBlock: { marginTop: spacing.sm, gap: 6, backgroundColor: colors.surface, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, padding: spacing.sm },
  observationQuestion: { fontSize: 14, lineHeight: 19, fontWeight: "800", color: colors.onSurface },
  observationOption: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 40, paddingHorizontal: 4 },
  observationOptionText: { fontSize: 14, color: colors.onSurface, fontWeight: "600" },
  stopCard: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start", backgroundColor: "#FBECEC", borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.md },
  stopText: { flex: 1, fontSize: 13, lineHeight: 19, color: "#7C2B2B", fontWeight: "600" },
  doneBanner: { flexDirection: "row", gap: spacing.sm, alignItems: "center", backgroundColor: "#E2F1E7", borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.md },
  doneBannerText: { flex: 1, fontSize: 14, lineHeight: 20, color: "#1F7047", fontWeight: "700" },
  card: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.md, gap: 6 },
  cardTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  domain: { fontSize: 13, fontWeight: "800", color: colors.brandPrimary, textTransform: "uppercase", letterSpacing: 0.6 },
  goal: { fontSize: 17, lineHeight: 23, fontWeight: "800", color: colors.onSurface },
  muscles: { fontSize: 13, lineHeight: 18, color: colors.onSurfaceSecondary, fontWeight: "600" },
  stepRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start", marginTop: 4 },
  stepNumber: { width: 22, height: 22, borderRadius: 11, backgroundColor: colors.brandTertiary, color: colors.onBrandTertiary, textAlign: "center", fontSize: 12, lineHeight: 22, fontWeight: "800", overflow: "hidden" },
  stepText: { flex: 1, fontSize: 14, lineHeight: 20, color: colors.onSurface },
  dose: { fontSize: 13, lineHeight: 18, color: colors.onSurfaceSecondary, marginTop: 4, fontStyle: "italic" },
  safety: { fontSize: 13, lineHeight: 18, color: "#7C2B2B" },
  doneBtn: { marginTop: spacing.sm, minHeight: 46, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  doneBtnDone: { backgroundColor: "#E2F1E7" },
  doneBtnText: { color: colors.onBrandPrimary, fontSize: 15, fontWeight: "800" },
  doneBtnTextDone: { color: "#1F7047" },
  errorText: { color: colors.error, fontSize: 14, lineHeight: 20, marginVertical: spacing.md },
});
