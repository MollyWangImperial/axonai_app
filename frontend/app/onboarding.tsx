import { useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ScrollView, ActivityIndicator, KeyboardAvoidingView, Modal, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { authedFetch, cachePatientOnboarding, getCachedUser, signIn } from "@/src/auth";

type Step = {
  key: string;
  question: string;
  helper?: string;
  type: "text" | "number" | "single" | "multi";
  options?: { value: string; label: string; emoji?: string }[];
  optional?: boolean;
};

const STEPS: Step[] = [
  { key: "preferred_name", question: "What should we call you?", helper: "We'll use this name in your exercises and check-ins.", type: "text" },
  { key: "age_band", question: "Which age range are you in?", type: "single",
    options: [
      { value: "under_20", label: "Under 20" },
      { value: "20-29", label: "20 - 29" },
      { value: "30-39", label: "30 - 39" },
      { value: "40-49", label: "40 - 49" },
      { value: "50-59", label: "50 - 59" },
      { value: "60-69", label: "60 - 69" },
      { value: "70-79", label: "70 - 79" },
      { value: "80+", label: "80 or older" },
    ] },
  { key: "gender", question: "How do you describe your gender?", helper: "Choose the answer that feels right for you.", type: "single",
    options: [
      { value: "female", label: "Female" },
      { value: "male", label: "Male" },
      { value: "transgender_woman", label: "Transgender woman" },
      { value: "transgender_man", label: "Transgender man" },
      { value: "non_binary", label: "Non-binary" },
      { value: "self_describe", label: "Another gender identity" },
      { value: "prefer_not_to_say", label: "Prefer not to say" },
    ] },
  { key: "months_since_stroke", question: "Roughly how many months since your stroke?", helper: "An estimate is fine — this helps tune your plan to your recovery stage.", type: "number" },
  { key: "affected_areas", question: "Which areas of your body were affected?", helper: "Select every area that applies.", type: "multi",
    options: [
      { value: "left_upper", label: "Left upper limb (shoulder, arm or hand)" },
      { value: "left_lower", label: "Left lower limb (hip, leg or foot)" },
      { value: "right_upper", label: "Right upper limb (shoulder, arm or hand)" },
      { value: "right_lower", label: "Right lower limb (hip, leg or foot)" },
      { value: "face_speech", label: "Face or speech" },
      { value: "other", label: "Another area" },
      { value: "unsure", label: "Not sure yet" },
    ] },
  { key: "dominant_hand", question: "Which is your dominant hand (before stroke)?", type: "single",
    options: [
      { value: "right", label: "Right-handed", emoji: "✋" },
      { value: "left", label: "Left-handed", emoji: "🤚" },
      { value: "ambidextrous", label: "Both / Ambidextrous", emoji: "🙌" },
    ] },
  { key: "mobility_level", question: "How do you usually get around?", type: "single",
    options: [
      { value: "independent", label: "I walk independently", emoji: "🚶" },
      { value: "cane", label: "With a cane", emoji: "🦯" },
      { value: "walker", label: "With a walker / frame", emoji: "🚶‍♀️" },
      { value: "wheelchair", label: "I use a wheelchair", emoji: "♿" },
    ] },
  { key: "primary_goal", question: "What's the one thing you'd love to do again?", helper: "Examples: hold my grandchild, eat with a fork, button my own shirt, paint, type at the computer.", type: "text" },
  { key: "secondary_goals", question: "Any other goals? Tap all that apply.", type: "multi",
    options: [
      { value: "reach_overhead", label: "Reach overhead", emoji: "🙆" },
      { value: "self_feed", label: "Self-feed", emoji: "🍽️" },
      { value: "dress", label: "Dress independently", emoji: "👔" },
      { value: "write", label: "Write / draw", emoji: "✍️" },
      { value: "drive", label: "Drive again", emoji: "🚗" },
      { value: "cook", label: "Cook", emoji: "🍳" },
      { value: "play_music", label: "Play music", emoji: "🎸" },
      { value: "exercise", label: "Exercise / sports", emoji: "🏃" },
      { value: "other", label: "Other" },
    ], optional: true },
  { key: "medical_conditions", question: "Do you have any pre-existing medical conditions?", helper: "Select all that apply. This helps us keep guidance appropriate and safe.", type: "multi",
    options: [
      { value: "hypertension", label: "High blood pressure" },
      { value: "arthritis", label: "Arthritis" },
      { value: "heart_condition", label: "Heart condition" },
      { value: "diabetes", label: "Diabetes" },
      { value: "cancer", label: "Cancer" },
      { value: "other", label: "Another condition" },
      { value: "none", label: "None of these" },
    ], optional: true },
  { key: "has_caregiver", question: "Is someone helping you at home (family, caregiver)?", type: "single",
    options: [
      { value: "yes", label: "Yes — I have help", emoji: "🤝" },
      { value: "no", label: "No, mostly on my own", emoji: "🌿" },
    ] },
];

export default function OnboardingScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
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
  const [saveError, setSaveError] = useState<string | null>(null);

  const step = STEPS[idx];
  const progress = ((idx + 1) / STEPS.length) * 100;

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
    if (idx < STEPS.length - 1) {
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
        router.replace("/");
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
    if (idx < STEPS.length - 1) {
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
                style={[styles.chip, active && styles.chipActive]}
              >
                {o.emoji && <Text style={styles.chipEmoji}>{o.emoji}</Text>}
                <Text style={[styles.chipText, active && styles.chipTextActive]}>{o.label}</Text>
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
        <Pressable onPress={() => idx > 0 && setIdx(idx - 1)} disabled={idx === 0} hitSlop={12}>
          <Ionicons name="chevron-back" size={26} color={idx === 0 ? colors.onSurfaceTertiary : colors.onSurface} />
        </Pressable>
        <Text style={styles.stepCounter}>{idx + 1} of {STEPS.length}</Text>
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
          {renderInput()}
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
          {saveError && (
            <Text testID="onb-save-error" accessibilityRole="alert" style={styles.saveError}>
              {saveError}
            </Text>
          )}
          <Pressable
            testID="onb-continue"
            disabled={!canContinue() || saving}
            onPress={onContinue}
            style={[styles.continueBtn, (!canContinue() || saving) && styles.continueBtnDisabled]}
          >
            {saving ? <ActivityIndicator color="#fff" /> :
              <Text style={styles.continueText}>{idx === STEPS.length - 1 ? "Finish" : "Continue"}</Text>}
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
