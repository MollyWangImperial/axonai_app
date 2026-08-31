import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ScrollView, ActivityIndicator, KeyboardAvoidingView, Modal, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { authedFetch, cachePatientOnboarding, getCachedUser, signIn } from "@/src/auth";
import { ASSESSMENT_READINESS_KEYS, PATIENT_SURVEY_STEPS } from "@/src/patientSurvey";

const READINESS_SURVEY_STEPS = PATIENT_SURVEY_STEPS.filter((item) =>
  ASSESSMENT_READINESS_KEYS.includes(item.key as typeof ASSESSMENT_READINESS_KEYS[number]),
);

// "Any other goals?" shows a picture for each option instead of a symbol:
// large pictograms on tinted cards, with a check mark when selected.
const GOAL_PICTURES: Record<string, { icon: keyof typeof MaterialCommunityIcons.glyphMap; tint: string; background: string }> = {
  reach_overhead: { icon: "human-handsup", tint: "#1F6A4A", background: "#E4F1E8" },
  self_feed: { icon: "silverware-fork-knife", tint: "#8A5A00", background: "#FBF0DB" },
  dress: { icon: "tshirt-crew", tint: "#28618C", background: "#E3EEF7" },
  write: { icon: "lead-pencil", tint: "#6B4A9B", background: "#EDE7F7" },
  drive: { icon: "car-side", tint: "#A34A2A", background: "#FBE9E1" },
  cook: { icon: "chef-hat", tint: "#8A5A00", background: "#FBF0DB" },
  play_music: { icon: "guitar-acoustic", tint: "#8C2E52", background: "#F9E6EE" },
  exercise: { icon: "run", tint: "#1F6A4A", background: "#E4F1E8" },
  other: { icon: "star-plus-outline", tint: "#4E5A52", background: "#EEF1EE" },
};

export default function OnboardingScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ mode?: string }>();
  const isReadinessUpdate = params.mode === "assessment-readiness";
  // Never re-ask what the survey already answered: readiness mode only shows
  // the still-missing questions, and skips itself entirely when none remain.
  const [readinessSteps, setReadinessSteps] = useState<typeof READINESS_SURVEY_STEPS | null>(null);
  const steps = isReadinessUpdate
    ? (readinessSteps ?? READINESS_SURVEY_STEPS)
    : PATIENT_SURVEY_STEPS;
  const [idx, setIdx] = useState(0);
  const [values, setValues] = useState<Record<string, any>>({});
  const [textInput, setTextInput] = useState("");
  const [otherAreaText, setOtherAreaText] = useState("");
  const [showOtherArea, setShowOtherArea] = useState(false);
  const [otherGoalText, setOtherGoalText] = useState("");
  const [showOtherGoal, setShowOtherGoal] = useState(false);
  const [otherConditionText, setOtherConditionText] = useState("");
  const [showOtherCondition, setShowOtherCondition] = useState(false);
  const [genderDescription, setGenderDescription] = useState("");
  const [showGenderDescription, setShowGenderDescription] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingProfile, setLoadingProfile] = useState(isReadinessUpdate);
  const [saveError, setSaveError] = useState<string | null>(null);

  const step = steps[idx];
  const progress = ((idx + 1) / steps.length) * 100;

  useEffect(() => {
    if (!isReadinessUpdate) return;
    let active = true;
    (async () => {
      try {
        const response = await authedFetch("/api/users/onboarding");
        if (!response.ok) throw new Error("PROFILE_LOAD_FAILED");
        const body = await response.json();
        if (!active) return;
        const savedProfile = body?.profile || {};
        setValues(savedProfile);
        const answered = (value: any) => {
          if (value == null) return false;
          if (Array.isArray(value)) return value.length > 0;
          return String(value).trim() !== "";
        };
        const missingSteps = READINESS_SURVEY_STEPS.filter((item) => !answered(savedProfile[item.key]));
        if (missingSteps.length === 0) {
          // The survey already covers every readiness question - go straight
          // to task selection instead of repeating them.
          router.replace("/task-intro?mode=initial" as never);
          return;
        }
        setReadinessSteps(missingSteps);
      } catch {
        if (active) setSaveError("We couldn't load your saved survey. Check your connection and try again.");
      } finally {
        if (active) setLoadingProfile(false);
      }
    })();
    return () => { active = false; };
  }, [isReadinessUpdate, router]);

  const setVal = (k: string, v: any) => setValues((prev) => ({ ...prev, [k]: v }));

  const canContinue = () => {
    if (step.optional) return true;
    const v = values[step.key];
    if (step.type === "text") return (textInput || v || "").toString().trim().length > 0;
    if (step.type === "number") return !!textInput && !isNaN(parseInt(textInput, 10));
    if (step.type === "multi") return Array.isArray(v) && v.length > 0;
    return !!v;
  };

  const onContinue = async () => {
    Haptics.selectionAsync();
    setSaveError(null);
    let next = { ...values };
    if (step.type === "text") next[step.key] = textInput.trim();
    else if (step.type === "number") next[step.key] = parseInt(textInput, 10);
    setValues(next);
    setTextInput("");
    if (idx < steps.length - 1) {
      setIdx(idx + 1);
    } else {
      setSaving(true);
      try {
        const payload: any = { ...next };
        const areas: string[] = payload.affected_areas || [];
        const hasLeft = areas.some((area) => area.startsWith("left_"));
        const hasRight = areas.some((area) => area.startsWith("right_"));
        payload.side_affected = hasLeft && hasRight ? "both" : hasLeft ? "left" : hasRight ? "right" : "unsure";
        // map yes/no → boolean
        if (payload.has_caregiver === "yes") payload.has_caregiver = true;
        else if (payload.has_caregiver === "no") payload.has_caregiver = false;
        const submit = (userId?: string) => authedFetch("/api/users/onboarding", {
          method: "POST",
          headers: userId ? { "X-User-Id": userId } : undefined,
          body: JSON.stringify(payload),
        });

        let response = await submit();
        if (response.status === 401) {
          const cachedUser = await getCachedUser();
          if (!cachedUser?.email) throw new Error("SESSION_EXPIRED");
          const refreshedUser = await signIn(cachedUser.email, cachedUser.name, cachedUser.role);
          response = await submit(refreshedUser.id);
        }

        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(body?.detail || `SAVE_FAILED_${response.status}`);
        }

        // These caches improve startup speed, but the saved server profile remains
        // authoritative if browser or device storage is unavailable.
        const savedUser = await getCachedUser();
        if (savedUser?.id) await cachePatientOnboarding(savedUser.id, payload);

        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        router.replace(isReadinessUpdate ? "/task-intro?mode=initial" : "/");
      } catch (error) {
        const message = error instanceof Error ? error.message : "";
        setSaveError(
          message === "SESSION_EXPIRED" || message === "Sign in required"
            ? "Your session expired. Please sign in again, then tap Finish."
            : "We couldn't save your profile. Check your connection and tap Finish again.",
        );
        setSaving(false);
      }
    }
  };

  const onSkip = async () => {
    if (idx < steps.length - 1) {
      setIdx(idx + 1);
      setTextInput("");
      return;
    }
    // last step optional skip → finish anyway
    await onContinue();
  };

  const renderInput = () => {
    if (step.type === "text" || step.type === "number") {
      return (
        <TextInput
          testID={`onb-input-${step.key}`}
          value={textInput}
          onChangeText={setTextInput}
          placeholder={step.type === "number" ? "e.g. 6" : "Type here…"}
          placeholderTextColor={colors.onSurfaceTertiary}
          keyboardType={step.type === "number" ? "number-pad" : "default"}
          autoFocus
          style={styles.textInput}
        />
      );
    }
    if (step.type === "single") {
      return (
        <View style={styles.optionsCol}>
          {step.options!.map((o) => {
            const active = values[step.key] === o.value;
            return (
              <Pressable
                key={o.value}
                testID={`onb-opt-${step.key}-${o.value}`}
                onPress={() => {
                  if (step.key === "gender" && o.value === "self_describe") {
                    setShowGenderDescription(true);
                    return;
                  }
                  setVal(step.key, o.value);
                  if (step.key === "gender") setVal("gender_self_description", undefined);
                }}
                style={[styles.optionRow, active && styles.optionRowActive]}
              >
                {o.emoji && <Text style={styles.optionEmoji}>{o.emoji}</Text>}
                <Text style={[styles.optionLabel, active && styles.optionLabelActive]}>{o.label}</Text>
                {active && <Ionicons name="checkmark-circle" size={22} color={colors.brandPrimary} />}
              </Pressable>
            );
          })}
        </View>
      );
    }
    if (step.type === "multi") {
      const selected: string[] = values[step.key] || [];
      return (
        <View style={styles.optionsGrid}>
          {step.options!.map((o) => {
            const active = selected.includes(o.value);
            return (
              <Pressable
                key={o.value}
                testID={`onb-multi-${step.key}-${o.value}`}
                onPress={() => {
                  if (step.key === "affected_areas" && o.value === "other") {
                    if (active) {
                      setVal(step.key, selected.filter((s) => s !== "other"));
                      setVal("affected_areas_other", undefined);
                      setOtherAreaText("");
                    } else {
                      setShowOtherArea(true);
                    }
                    return;
                  }
                  if (step.key === "medical_conditions" && o.value === "other") {
                    if (active) {
                      setVal(step.key, selected.filter((s) => s !== "other"));
                      setVal("medical_conditions_other", undefined);
                      setOtherConditionText("");
                    } else {
                      setShowOtherCondition(true);
                    }
                    return;
                  }
                  if (step.key === "secondary_goals" && o.value === "other") {
                    if (active) {
                      setVal(step.key, selected.filter((s) => s !== "other"));
                      setVal("secondary_goals_other", undefined);
                      setOtherGoalText("");
                    } else {
                      setShowOtherGoal(true);
                    }
                    return;
                  }
                  let next: string[];
                  if (o.value === "none") {
                    next = active ? [] : ["none"];
                    setVal("medical_conditions_other", undefined);
                    setOtherConditionText("");
                  }
                  else next = active ? selected.filter((s) => s !== o.value) : [...selected.filter((s) => s !== "none"), o.value];
                  setVal(step.key, next);
                }}
                style={step.key === "secondary_goals"
                  ? [styles.goalCard, active && styles.goalCardActive]
                  : [styles.chip, active && styles.chipActive]}
              >
                {step.key === "secondary_goals" ? (
                  <>
                    <View style={[styles.goalPicture, { backgroundColor: (GOAL_PICTURES[o.value] || GOAL_PICTURES.other).background }]} testID={`goal-picture-${o.value}`}>
                      <MaterialCommunityIcons
                        name={(GOAL_PICTURES[o.value] || GOAL_PICTURES.other).icon}
                        size={44}
                        color={(GOAL_PICTURES[o.value] || GOAL_PICTURES.other).tint}
                      />
                    </View>
                    <Text style={[styles.goalCardText, active && styles.goalCardTextActive]}>{o.label}</Text>
                    {active && (
                      <View style={styles.goalCheck}>
                        <Ionicons name="checkmark-circle" size={24} color={colors.brandPrimary} />
                      </View>
                    )}
                  </>
                ) : (
                  <>
                    {o.emoji && <Text style={styles.chipEmoji}>{o.emoji}</Text>}
                    <Text style={[styles.chipText, active && styles.chipTextActive]}>{o.label}</Text>
                  </>
                )}
              </Pressable>
            );
          })}
        </View>
      );
    }
    return null;
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.sm }]}>
      <View style={styles.topBar}>
        <Pressable onPress={() => idx > 0 ? setIdx(idx - 1) : isReadinessUpdate ? router.back() : undefined} disabled={idx === 0 && !isReadinessUpdate} hitSlop={12}>
          <Ionicons name="chevron-back" size={26} color={idx === 0 && !isReadinessUpdate ? colors.onSurfaceTertiary : colors.onSurface} />
        </Pressable>
        <Text style={styles.stepCounter}>{isReadinessUpdate ? "Assessment readiness" : `${idx + 1} of ${steps.length}`}</Text>
        {step.optional ? (
          <Pressable onPress={onSkip} testID="onb-skip" hitSlop={12}>
            <Text style={styles.skip}>Skip</Text>
          </Pressable>
        ) : <View style={{ width: 40 }} />}
      </View>
      <View style={styles.progressBg}>
        <View style={[styles.progressFill, { width: `${progress}%` }]} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <Text style={styles.question} testID={`onb-q-${step.key}`}>{step.question}</Text>
          {step.helper && <Text style={styles.helper}>{step.helper}</Text>}
          <View style={{ height: spacing.lg }} />
          {loadingProfile ? <ActivityIndicator color={colors.brandPrimary} /> : renderInput()}
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
          {saveError && (
            <Text testID="onb-save-error" accessibilityRole="alert" style={styles.saveError}>
              {saveError}
            </Text>
          )}
          <Pressable
            testID="onb-continue"
            disabled={!canContinue() || saving || loadingProfile}
            onPress={onContinue}
            style={[styles.continueBtn, (!canContinue() || saving || loadingProfile) && styles.continueBtnDisabled]}
          >
            {saving ? <ActivityIndicator color="#fff" /> :
              <Text style={styles.continueText}>{idx === steps.length - 1 ? isReadinessUpdate ? "Save and select tasks" : "Finish" : "Continue"}</Text>}
          </Pressable>
        </View>
      </KeyboardAvoidingView>

      <Modal
        visible={showOtherArea}
        transparent
        animationType="fade"
        onRequestClose={() => {
          setShowOtherArea(false);
          setOtherAreaText("");
        }}
      >
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.modalBackdrop}>
          <View style={styles.modalPanel}>
            <Text style={styles.modalTitle}>Tell us which other area was affected</Text>
            <Text style={styles.modalHelper}>A short description is enough.</Text>
            <TextInput
              testID="onb-other-area-input"
              value={otherAreaText}
              onChangeText={setOtherAreaText}
              placeholder="Type the affected body area"
              placeholderTextColor={colors.onSurfaceTertiary}
              multiline
              autoFocus
              style={styles.modalInput}
            />
            <View style={styles.modalActions}>
              <Pressable
                testID="onb-other-area-cancel"
                onPress={() => {
                  setShowOtherArea(false);
                  setOtherAreaText("");
                }}
                style={styles.modalCancel}
              >
                <Text style={styles.modalCancelText}>Cancel</Text>
              </Pressable>
              <Pressable
                testID="onb-other-area-save"
                disabled={!otherAreaText.trim()}
                onPress={() => {
                  const description = otherAreaText.trim();
                  if (!description) return;
                  const selected: string[] = values.affected_areas || [];
                  setValues((prev) => ({
                    ...prev,
                    affected_areas: [...selected.filter((item) => item !== "other"), "other"],
                    affected_areas_other: description,
                  }));
                  setShowOtherArea(false);
                }}
                style={[styles.modalSave, !otherAreaText.trim() && styles.modalSaveDisabled]}
              >
                <Text style={styles.modalSaveText}>Save</Text>
              </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      <Modal
        visible={showGenderDescription}
        transparent
        animationType="fade"
        onRequestClose={() => setShowGenderDescription(false)}
      >
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.modalBackdrop}>
          <View style={styles.modalPanel}>
            <Text style={styles.modalTitle}>Tell us how you describe your gender</Text>
            <Text style={styles.modalHelper}>Use the words that feel right for you.</Text>
            <TextInput
              testID="onb-gender-description-input"
              value={genderDescription}
              onChangeText={setGenderDescription}
              placeholder="Type your gender identity"
              placeholderTextColor={colors.onSurfaceTertiary}
              autoFocus
              style={styles.modalInput}
            />
            <View style={styles.modalActions}>
              <Pressable testID="onb-gender-description-cancel" onPress={() => { setShowGenderDescription(false); setGenderDescription(""); }} style={styles.modalCancel}>
                <Text style={styles.modalCancelText}>Cancel</Text>
              </Pressable>
              <Pressable
                testID="onb-gender-description-save"
                disabled={!genderDescription.trim()}
                onPress={() => {
                  const description = genderDescription.trim();
                  if (!description) return;
                  setValues((previous) => ({ ...previous, gender: "self_describe", gender_self_description: description }));
                  setShowGenderDescription(false);
                }}
                style={[styles.modalSave, !genderDescription.trim() && styles.modalSaveDisabled]}
              >
                <Text style={styles.modalSaveText}>Save</Text>
              </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      <Modal
        visible={showOtherGoal}
        transparent
        animationType="fade"
        onRequestClose={() => {
          setShowOtherGoal(false);
          setOtherGoalText("");
        }}
      >
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.modalBackdrop}>
          <View style={styles.modalPanel}>
            <Text style={styles.modalTitle}>Tell us about your other goal</Text>
            <Text style={styles.modalHelper}>Describe something you would like to be able to do again.</Text>
            <TextInput
              testID="onb-other-goal-input"
              value={otherGoalText}
              onChangeText={setOtherGoalText}
              placeholder="Type your goal"
              placeholderTextColor={colors.onSurfaceTertiary}
              multiline
              autoFocus
              style={styles.modalInput}
            />
            <View style={styles.modalActions}>
              <Pressable
                testID="onb-other-goal-cancel"
                onPress={() => {
                  setShowOtherGoal(false);
                  setOtherGoalText("");
                }}
                style={styles.modalCancel}
              >
                <Text style={styles.modalCancelText}>Cancel</Text>
              </Pressable>
              <Pressable
                testID="onb-other-goal-save"
                disabled={!otherGoalText.trim()}
                onPress={() => {
                  const description = otherGoalText.trim();
                  if (!description) return;
                  const selected: string[] = values.secondary_goals || [];
                  setValues((prev) => ({
                    ...prev,
                    secondary_goals: [...selected.filter((item) => item !== "other"), "other"],
                    secondary_goals_other: description,
                  }));
                  setShowOtherGoal(false);
                }}
                style={[styles.modalSave, !otherGoalText.trim() && styles.modalSaveDisabled]}
              >
                <Text style={styles.modalSaveText}>Save</Text>
              </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      <Modal
        visible={showOtherCondition}
        transparent
        animationType="fade"
        onRequestClose={() => setShowOtherCondition(false)}
      >
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.modalBackdrop}>
          <View style={styles.modalPanel}>
            <Text style={styles.modalTitle}>Tell us about the other condition</Text>
            <Text style={styles.modalHelper}>A short description of the condition or symptoms is enough.</Text>
            <TextInput
              testID="onb-other-condition-input"
              value={otherConditionText}
              onChangeText={setOtherConditionText}
              placeholder="Type the condition or symptoms"
              placeholderTextColor={colors.onSurfaceTertiary}
              multiline
              autoFocus
              style={styles.modalInput}
            />
            <View style={styles.modalActions}>
              <Pressable
                testID="onb-other-condition-cancel"
                onPress={() => {
                  setShowOtherCondition(false);
                  setOtherConditionText("");
                }}
                style={styles.modalCancel}
              >
                <Text style={styles.modalCancelText}>Cancel</Text>
              </Pressable>
              <Pressable
                testID="onb-other-condition-save"
                disabled={!otherConditionText.trim()}
                onPress={() => {
                  const description = otherConditionText.trim();
                  if (!description) return;
                  const selected: string[] = values.medical_conditions || [];
                  setValues((prev) => ({
                    ...prev,
                    medical_conditions: [...selected.filter((item) => item !== "none" && item !== "other"), "other"],
                    medical_conditions_other: description,
                  }));
                  setShowOtherCondition(false);
                }}
                style={[styles.modalSave, !otherConditionText.trim() && styles.modalSaveDisabled]}
              >
                <Text style={styles.modalSaveText}>Save</Text>
              </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  topBar: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.md, paddingBottom: spacing.sm },
  stepCounter: { color: colors.onSurfaceSecondary, fontSize: 14, fontWeight: "600" },
  skip: { color: colors.brandPrimary, fontSize: 15, fontWeight: "700" },
  progressBg: { height: 4, backgroundColor: colors.divider, marginHorizontal: spacing.lg, borderRadius: 2, overflow: "hidden" },
  progressFill: { height: 4, backgroundColor: colors.brandPrimary, borderRadius: 2 },
  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.xl, paddingBottom: spacing.xl },
  question: { fontSize: 26, fontWeight: "800", color: colors.onSurface, lineHeight: 32 },
  helper: { fontSize: 15, color: colors.onSurfaceSecondary, lineHeight: 22, marginTop: spacing.sm },
  textInput: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, color: colors.onSurface, fontSize: 18, minHeight: 56 },
  optionsCol: { gap: spacing.sm },
  optionRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, padding: spacing.md, borderRadius: radius.lg, borderWidth: 2, borderColor: "transparent", minHeight: 60 },
  optionRowActive: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  optionEmoji: { fontSize: 24 },
  optionLabel: { flex: 1, fontSize: 16, fontWeight: "600", color: colors.onSurface },
  optionLabelActive: { color: colors.onBrandTertiary, fontWeight: "700" },
  optionsGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { maxWidth: "100%", flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.surfaceSecondary, paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 2, borderColor: "transparent" },
  chipActive: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipEmoji: { fontSize: 16 },
  goalCard: { width: "47%", flexGrow: 1, alignItems: "center", gap: spacing.sm, paddingVertical: spacing.md, paddingHorizontal: spacing.sm, borderRadius: radius.md, borderWidth: 2, borderColor: colors.border, backgroundColor: colors.surface, position: "relative" },
  goalCardActive: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  goalPicture: { width: 76, height: 76, borderRadius: 38, alignItems: "center", justifyContent: "center" },
  goalCardText: { fontSize: 14, lineHeight: 19, fontWeight: "800", color: colors.onSurface, textAlign: "center" },
  goalCardTextActive: { color: colors.brandPrimary },
  goalCheck: { position: "absolute", top: 8, right: 8 },
  chipText: { flexShrink: 1, fontSize: 14, lineHeight: 19, fontWeight: "600", color: colors.onSurface },
  chipTextActive: { color: colors.onBrandTertiary, fontWeight: "700" },
  footer: { padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider },
  saveError: { color: colors.error, fontSize: 14, lineHeight: 20, marginBottom: spacing.sm, textAlign: "center" },
  continueBtn: { backgroundColor: colors.brandPrimary, padding: 16, borderRadius: radius.lg, alignItems: "center", minHeight: 56, justifyContent: "center" },
  continueBtnDisabled: { opacity: 0.4 },
  continueText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "800" },
  modalBackdrop: { flex: 1, justifyContent: "center", padding: spacing.lg, backgroundColor: "rgba(0, 0, 0, 0.42)" },
  modalPanel: { width: "100%", maxWidth: 460, alignSelf: "center", backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  modalTitle: { color: colors.onSurface, fontSize: 20, lineHeight: 26, fontWeight: "800" },
  modalHelper: { color: colors.onSurfaceSecondary, fontSize: 14, lineHeight: 20, marginTop: spacing.xs },
  modalInput: { minHeight: 112, maxHeight: 180, marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, color: colors.onSurface, fontSize: 16, lineHeight: 22, textAlignVertical: "top" },
  modalActions: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.md },
  modalCancel: { minHeight: 46, minWidth: 92, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  modalCancelText: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  modalSave: { minHeight: 46, minWidth: 92, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md, borderRadius: radius.md, backgroundColor: colors.brandPrimary },
  modalSaveDisabled: { opacity: 0.4 },
  modalSaveText: { color: colors.onBrandPrimary, fontSize: 15, fontWeight: "800" },
});
