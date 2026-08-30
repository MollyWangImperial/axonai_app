import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";

import { colors, spacing, radius } from "@/src/theme";
import { loadSettings, rescheduleReminders } from "@/src/utils/notifications";
import { SurveyPrefaceModal } from "@/src/components/SurveyPrefaceModal";

type NextStepAction = {
  action: string;
  title: string;
  message: string;
  cta: string;
  destination: string;
  secondary_action?: NextStepAction | null;
};

export type AliraCarePlan = {
  survey?: {
    due?: boolean;
    due_at?: string;
    patient_prompt_enabled?: boolean;
  };
  assessment?: {
    due?: boolean;
    due_at?: string;
    blocked_by_safety?: boolean;
    can_start?: boolean;
    packages?: string[];
    task_ids?: string[];
  };
  exercise_plan?: {
    action?: string;
    approved_exercise_ids?: string[];
  };
  next_step?: NextStepAction;
};

type Props = {
  name: string;
  plan: AliraCarePlan | null;
  latestAssessmentId?: string;
};

export function DailyCheckInCard({ name, plan, latestAssessmentId }: Props) {
  const router = useRouter();
  const [showPreface, setShowPreface] = useState(false);
  const nextStep: NextStepAction = plan?.next_step ?? {
    action: latestAssessmentId ? "review_progress" : "initial_assessment",
    title: latestAssessmentId ? "Review your recovery progress" : "Complete your initial assessment",
    message: latestAssessmentId
      ? "Your latest recovery information is ready to review."
      : "Your first movement assessment is the next step.",
    cta: latestAssessmentId ? "See your progress" : "Start initial assessment",
    destination: latestAssessmentId ? "progress" : "initial_assessment",
    secondary_action: null,
  };
  const secondarySurvey = nextStep.secondary_action?.action === "recovery_check_in"
    ? nextStep.secondary_action
    : null;
  const surveyIsPrimary = nextStep.action === "recovery_check_in";

  useEffect(() => {
    if (!plan) return;
    void loadSettings().then((settings) => rescheduleReminders(settings, plan));
  }, [plan]);

  const openSurveyChat = () => {
    setShowPreface(false);
    router.push({
      pathname: "/(tabs)/chat" as never,
      params: { prompt: "Please begin my scheduled short recovery check-in." },
    });
  };

  const openPrimaryAction = () => {
    Haptics.selectionAsync();
    switch (nextStep.destination) {
      case "survey":
        setShowPreface(true);
        return;
      case "initial_assessment":
        router.push({
          pathname: "/session-check" as never,
          params: {
            target: "assessment",
            mode: "initial",
            package: "initial",
            task_ids: (plan?.assessment?.task_ids || []).join(","),
          },
        });
        return;
      case "assessment":
        router.push({
          pathname: "/session-check" as never,
          params: {
            target: "assessment",
            mode: "followup",
            package: plan?.assessment?.packages?.[0] || "upper_limb",
            task_ids: (plan?.assessment?.task_ids || []).join(","),
          },
        });
        return;
      case "rehab_plan":
        if (latestAssessmentId) router.push({ pathname: "/rehab-plan", params: { id: latestAssessmentId } });
        else router.push("/(tabs)/journey" as never);
        return;
      case "emergency":
        router.push("/(tabs)/emergency" as never);
        return;
      case "alira":
        router.push({
          pathname: "/(tabs)/chat" as never,
          params: {
            prompt: nextStep.action === "initial_assessment"
              ? "Please help me finish my initial assessment setup."
              : "Please guide me through the next safe step.",
          },
        });
        return;
      default:
        router.push("/progress" as never);
    }
  };

  const iconName = nextStep.action === "continue_exercises"
    ? "fitness-outline"
    : nextStep.action === "initial_assessment" || nextStep.action === "movement_assessment"
      ? "clipboard-outline"
      : nextStep.action === "safety_follow_up"
        ? "warning-outline"
        : nextStep.action === "recovery_check_in"
          ? "chatbubble-ellipses-outline"
          : "trending-up-outline";

  return (
    <>
      <View style={styles.card} testID="daily-checkin-card">
        {secondarySurvey ? (
          <View style={styles.surveyBanner} testID="next-step-survey-secondary">
            <View style={styles.surveyBannerCopy}>
              <Text style={styles.surveyBannerTitle}>{secondarySurvey.title}</Text>
              <Text style={styles.surveyBannerBody}>{secondarySurvey.message}</Text>
            </View>
            <Pressable
              accessibilityRole="button"
              onPress={() => {
                Haptics.selectionAsync();
                setShowPreface(true);
              }}
              style={styles.surveyButton}
            >
              <Text style={styles.surveyButtonText}>Start</Text>
            </Pressable>
          </View>
        ) : null}

        <View style={styles.nextRow}>
          <View style={styles.avatar}><Ionicons name={iconName} size={21} color={colors.onBrandPrimary} /></View>
          <View style={styles.copy}>
            <View style={styles.topRow}>
              <Text style={styles.from}>Alira: Next step</Text>
              {surveyIsPrimary ? <View style={styles.duePill}><Text style={styles.dueText}>Check-in due</Text></View> : null}
            </View>
            <Text style={styles.greeting}>{name ? `${name}, ` : ""}{nextStep.title}</Text>
            <Text style={styles.body}>{nextStep.message}</Text>
            <Pressable
              testID="daily-checkin-chat"
              accessibilityRole="button"
              onPress={openPrimaryAction}
              style={styles.cta}
            >
              <Ionicons name="arrow-forward-circle-outline" size={17} color={colors.onBrandPrimary} />
              <Text style={styles.ctaText}>{nextStep.cta}</Text>
            </Pressable>
          </View>
        </View>
      </View>
      <SurveyPrefaceModal visible={showPreface} onBegin={openSurveyChat} onClose={() => setShowPreface(false)} />
    </>
  );
}

const styles = StyleSheet.create({
  card: { padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, marginBottom: spacing.md },
  surveyBanner: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.sm, marginBottom: spacing.md, borderRadius: radius.sm, backgroundColor: "#F8F1E8", borderWidth: 1, borderColor: "#E8CFAD" },
  surveyBannerCopy: { flex: 1, minWidth: 0 },
  surveyBannerTitle: { color: "#7B4A18", fontSize: 13, fontWeight: "900" },
  surveyBannerBody: { color: "#715B43", fontSize: 12, lineHeight: 17, marginTop: 2 },
  surveyButton: { minHeight: 36, paddingHorizontal: 14, alignItems: "center", justifyContent: "center", borderRadius: radius.pill, backgroundColor: "#FFFFFF" },
  surveyButtonText: { color: "#7B4A18", fontSize: 12, fontWeight: "900" },
  nextRow: { flexDirection: "row", gap: spacing.sm },
  avatar: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary },
  copy: { flex: 1, minWidth: 0 },
  topRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.sm },
  from: { fontSize: 13, fontWeight: "900", color: colors.brandPrimary, letterSpacing: 0 },
  duePill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill, backgroundColor: "#FCE9DA" },
  dueText: { fontSize: 12, fontWeight: "800", color: "#A94D1B" },
  greeting: { fontSize: 16, lineHeight: 22, fontWeight: "800", color: colors.onSurface, marginTop: 3 },
  body: { fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary, marginTop: 3 },
  cta: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", gap: 6, marginTop: spacing.sm, minHeight: 40, paddingVertical: 8, paddingHorizontal: 14, borderRadius: radius.pill, backgroundColor: colors.brandPrimary },
  ctaText: { fontSize: 13, fontWeight: "800", color: colors.onBrandPrimary },
});
