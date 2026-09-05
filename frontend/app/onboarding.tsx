import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ScrollView, ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Image, useWindowDimensions } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { authedFetch, cachePatientOnboarding, getCachedUser, signIn } from "@/src/auth";
import { ASSESSMENT_READINESS_KEYS, PATIENT_SURVEY_STEPS, MOVEMENT_READINESS_VERSION } from "@/src/patientSurvey";
import { getAgeAnatomyPresentation } from "@/src/ageAnatomy";

const READINESS_SURVEY_STEPS = PATIENT_SURVEY_STEPS.filter((item) =>
  ASSESSMENT_READINESS_KEYS.includes(item.key as typeof ASSESSMENT_READINESS_KEYS[number]),
);

const STANDING_OR_STEPPING_DIFFICULTIES = new Set([
  "sit_to_stand",
  "standing_balance",
  "weight_affected_leg",
  "start_step",
  "step_balance",
]);

const surveyStepApplies = (key: string, answers: Record<string, any>) => {
  if (key !== "standing_exercise_clearance") return true;
  const mobilityDifficulties = Array.isArray(answers.mobility_activity_difficulties)
    ? answers.mobility_activity_difficulties
    : [];
  return mobilityDifficulties.some((value: string) => STANDING_OR_STEPPING_DIFFICULTIES.has(value));
};

// The saved profile keeps the caregiver answer as a boolean, while the survey
// option values are "yes" / "no". Every other answer is stored as it was chosen.
const surveyAnswersFromProfile = (profile: Record<string, any>) => {
  const answers = { ...profile };
  if (typeof profile.has_caregiver === "boolean") answers.has_caregiver = profile.has_caregiver ? "yes" : "no";
  return answers;
};

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

const DOMINANT_HAND_PERSON = require("@/assets/images/survey-dominant-hand-person.png");
const DOMINANT_HANDS = require("@/assets/images/survey-dominant-hands.png");
const SITTING_INDEPENDENT = require("@/assets/images/survey-sitting-independent.png");
const SITTING_SUPPORTED = require("@/assets/images/survey-sitting-supported.png");
const SITTING_UNSAFE = require("@/assets/images/survey-sitting-unsafe.png");
const SITTING_UNSURE = require("@/assets/images/survey-sitting-unsure.png");
const ARM_MOVEMENT_MOST = require("@/assets/images/survey-arm-movement-most.png");
const ARM_MOVEMENT_SOME = require("@/assets/images/survey-arm-movement-some.png");
const ARM_MOVEMENT_HELP = require("@/assets/images/survey-arm-movement-help.png");
const ARM_MOVEMENT_NONE = require("@/assets/images/survey-arm-movement-none.png");
const ARM_MOVEMENT_UNAFFECTED = require("@/assets/images/survey-arm-movement-unaffected.png");
const ARM_MOVEMENT_UNSURE = require("@/assets/images/survey-arm-movement-unsure.png");

export default function OnboardingScreen() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const router = useRouter();
  const params = useLocalSearchParams<{ mode?: string }>();
  const isReadinessUpdate = params.mode === "assessment-readiness";
  // Refill mode (Settings → Survey questions → "Re-fill the survey") runs the
  // whole setup survey again for a patient who has already completed it. It
  // starts from the saved answers so only what has changed needs a new answer,
  // and nothing is written until the last step is saved.
  const isRefill = params.mode === "refill";
  const startsFromSavedProfile = isReadinessUpdate || isRefill;
  // Never re-ask what the survey already answered: readiness mode only shows
  // the still-missing questions, and skips itself entirely when none remain.
  const [readinessSteps, setReadinessSteps] = useState<typeof READINESS_SURVEY_STEPS | null>(null);
  const [idx, setIdx] = useState(0);
  const [values, setValues] = useState<Record<string, any>>({});
  const baseSteps = isReadinessUpdate
    ? (readinessSteps ?? READINESS_SURVEY_STEPS)
    : PATIENT_SURVEY_STEPS;
  const steps = baseSteps.filter((item) => surveyStepApplies(item.key, values));
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
  const [loadingProfile, setLoadingProfile] = useState(startsFromSavedProfile);
  const [saveError, setSaveError] = useState<string | null>(null);

  const step = steps[idx];
  const progress = ((idx + 1) / steps.length) * 100;
  const useWideAffectedAreaLayout = width >= 1180;
  const useWideDominantHandLayout = width >= 900;
  const useWideSittingAbilityLayout = width >= 1000;
  const useWideArmMovementLayout = width >= 1180;

  useEffect(() => {
    if (!startsFromSavedProfile) return;
    let active = true;
    (async () => {
      try {
        const response = await authedFetch("/api/users/onboarding");
        if (!response.ok) throw new Error("PROFILE_LOAD_FAILED");
        const body = await response.json();
        if (!active) return;
        const savedProfile = body?.profile || {};
        if (isRefill) {
          // Every question is asked again, pre-filled with the saved answer.
          setValues(surveyAnswersFromProfile(savedProfile));
          return;
        }
        setValues(savedProfile);
        const answered = (value: any) => {
          if (value == null) return false;
          if (Array.isArray(value)) return value.length > 0;
          return String(value).trim() !== "";
        };
        const usesLegacyMovementMeaning = savedProfile.movement_readiness_version !== MOVEMENT_READINESS_VERSION;
        const missingSteps = READINESS_SURVEY_STEPS.filter((item) => {
          if (!answered(savedProfile[item.key])) return true;
          return usesLegacyMovementMeaning
            && ["affected_arm_movement", "affected_hand_movement"].includes(item.key)
            && savedProfile[item.key] === "no_movement";
        });
        if (missingSteps.filter((item) => surveyStepApplies(item.key, savedProfile)).length === 0) {
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
  }, [startsFromSavedProfile, isRefill, router]);

  // Typed answers live in their own text box. Seed it from the current answer
  // whenever the question changes (and once the saved profile has loaded) so a
  // re-fill, or stepping back to an earlier question, shows what was answered
  // before instead of silently replacing it with an empty answer.
  useEffect(() => {
    if (!step || (step.type !== "text" && step.type !== "number")) return;
    const current = values[step.key];
    setTextInput(current == null ? "" : String(current));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step?.key, loadingProfile]);

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
        payload.movement_readiness_version = MOVEMENT_READINESS_VERSION;
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
        if (isReadinessUpdate) {
          router.replace("/task-intro?mode=initial" as never);
        } else if (isRefill) {
          // A re-fill is pushed on top of Settings → Survey questions; unwind
          // that stack back to Home, which reloads the updated profile on focus.
          router.dismissTo("/");
        } else {
          router.replace("/");
        }
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
      if (step.key === "dominant_hand") {
        const selectedHand = values.dominant_hand;
        const chooseHand = (value: "left" | "right" | "ambidextrous") => setVal("dominant_hand", value);
        const renderSideChoice = (value: "left" | "right", label: string) => {
          const active = selectedHand === value;
          return (
            <Pressable
              key={value}
              testID={`onb-opt-dominant_hand-${value}`}
              accessibilityRole="radio"
              accessibilityState={{ selected: active }}
              accessibilityLabel={`${label} handed`}
              onPress={() => chooseHand(value)}
              style={[
                styles.dominantSideChoice,
                useWideDominantHandLayout && styles.dominantSideChoiceWide,
                active && styles.dominantSideChoiceActive,
              ]}
            >
              <Text style={[styles.dominantSideLabel, active && styles.dominantSideLabelActive]}>{label}</Text>
              {active ? <Ionicons name="checkmark" size={useWideDominantHandLayout ? 34 : 25} color={colors.brandPrimary} /> : null}
            </Pressable>
          );
        };
        const bothSelected = selectedHand === "ambidextrous";
        const selectedSummary = selectedHand === "left"
          ? "Left-handed selected"
          : selectedHand === "right"
            ? "Right-handed selected"
            : null;

        return (
          <View
            testID="dominant-hand-selector"
            accessibilityRole="radiogroup"
            style={[styles.dominantHandLayout, useWideDominantHandLayout && styles.dominantHandLayoutWide]}
          >
            <View style={[styles.dominantPersonCard, useWideDominantHandLayout && styles.dominantPersonCardWide]}>
              <Text style={styles.dominantDirectionNote}>Same direction as you</Text>
              <View style={styles.dominantPersonRow}>
                {renderSideChoice("left", "LEFT")}
                <Image
                  source={DOMINANT_HAND_PERSON}
                  resizeMode="contain"
                  accessibilityLabel="Person shown from behind, facing the same direction as you"
                  style={[styles.dominantPersonImage, useWideDominantHandLayout && styles.dominantPersonImageWide]}
                />
                {renderSideChoice("right", "RIGHT")}
              </View>
              <View style={styles.dominantSelectionSummary}>
                {selectedSummary ? (
                  <>
                    <Ionicons name="checkmark-circle" size={24} color={colors.brandPrimary} />
                    <Text style={styles.dominantSelectionSummaryText}>{selectedSummary}</Text>
                  </>
                ) : (
                  <Text style={styles.dominantSelectionHint}>Choose left or right</Text>
                )}
              </View>
            </View>

            <Pressable
              testID="onb-opt-dominant_hand-ambidextrous"
              accessibilityRole="radio"
              accessibilityState={{ selected: bothSelected }}
              accessibilityLabel="Both hands or ambidextrous"
              onPress={() => chooseHand("ambidextrous")}
              style={[
                styles.dominantBothCard,
                useWideDominantHandLayout && styles.dominantBothCardWide,
                bothSelected && styles.dominantChoiceActive,
              ]}
            >
              <Image
                source={DOMINANT_HANDS}
                resizeMode="contain"
                accessibilityLabel="Two open hands"
                style={[styles.dominantHandsImage, useWideDominantHandLayout && styles.dominantHandsImageWide]}
              />
              <View style={styles.dominantBothCopy}>
                <View style={styles.dominantBothTitleRow}>
                  <Ionicons
                    name={bothSelected ? "checkmark-circle" : "ellipse-outline"}
                    size={28}
                    color={bothSelected ? colors.brandPrimary : colors.borderStrong}
                  />
                  <Text style={[styles.dominantBothEyebrow, bothSelected && styles.dominantSideLabelActive]}>BOTH</Text>
                </View>
                <Text style={styles.dominantBothTitle}>Both / Ambidextrous</Text>
                <Text style={styles.dominantBothDescription}>I used both hands about the same.</Text>
              </View>
            </Pressable>
          </View>
        );
      }

      if (step.key === "sitting_ability") {
        const selectedAbility = values.sitting_ability;
        const sittingChoices = [
          {
            value: "independent",
            label: "Yes, without someone holding me",
            image: SITTING_INDEPENDENT,
            imageLabel: "Person sitting upright independently in a stable chair",
          },
          {
            value: "needs_support",
            label: "Only with support or someone helping",
            image: SITTING_SUPPORTED,
            imageLabel: "Person sitting upright with another person helping",
          },
          {
            value: "unable",
            label: "No, not safely at the moment",
            image: SITTING_UNSAFE,
            imageLabel: "Stable chair beside a safety pause symbol",
          },
        ] as const;
        const renderChoiceIndicator = (active: boolean) => (
          <View style={[styles.sittingChoiceIndicator, active && styles.sittingChoiceIndicatorActive]}>
            {active ? <Ionicons name="checkmark" size={28} color={colors.onBrandPrimary} /> : null}
          </View>
        );

        return (
          <View
            testID="sitting-ability-selector"
            accessibilityRole="radiogroup"
            style={styles.sittingAbilityLayout}
          >
            <View style={[styles.sittingChoiceGrid, useWideSittingAbilityLayout && styles.sittingChoiceGridWide]}>
              {sittingChoices.map((choice) => {
                const active = selectedAbility === choice.value;
                return (
                  <Pressable
                    key={choice.value}
                    testID={`onb-opt-sitting_ability-${choice.value}`}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: active }}
                    accessibilityLabel={choice.label}
                    onPress={() => setVal("sitting_ability", choice.value)}
                    style={[
                      styles.sittingChoiceCard,
                      useWideSittingAbilityLayout && styles.sittingChoiceCardWide,
                      active && styles.sittingChoiceCardActive,
                    ]}
                  >
                    <Image
                      source={choice.image}
                      resizeMode="contain"
                      accessibilityLabel={choice.imageLabel}
                      style={[styles.sittingChoiceImage, useWideSittingAbilityLayout && styles.sittingChoiceImageWide]}
                    />
                    <Text style={[styles.sittingChoiceLabel, useWideSittingAbilityLayout && styles.sittingChoiceLabelWide]}>{choice.label}</Text>
                    {renderChoiceIndicator(active)}
                  </Pressable>
                );
              })}
            </View>

            <Pressable
              testID="onb-opt-sitting_ability-not_sure"
              accessibilityRole="radio"
              accessibilityState={{ selected: selectedAbility === "not_sure" }}
              accessibilityLabel="I am not sure"
              onPress={() => setVal("sitting_ability", "not_sure")}
              style={[
                styles.sittingUnsureChoice,
                selectedAbility === "not_sure" && styles.sittingChoiceCardActive,
              ]}
            >
              <Image source={SITTING_UNSURE} resizeMode="contain" accessibilityLabel="Chair with a question mark" style={styles.sittingUnsureImage} />
              <Text style={styles.sittingUnsureLabel}>I am not sure</Text>
              {renderChoiceIndicator(selectedAbility === "not_sure")}
            </Pressable>
          </View>
        );
      }

      if (step.key === "affected_arm_movement") {
        const selectedMovement = values.affected_arm_movement;
        const movementChoices = [
          {
            value: "most_movements",
            label: "Lift and reach",
            image: ARM_MOVEMENT_MOST,
            imageLabel: "Person lifting and reaching one arm overhead independently",
          },
          {
            value: "some_movement",
            label: "Some movement",
            image: ARM_MOVEMENT_SOME,
            imageLabel: "Person raising one arm part of the way independently",
          },
          {
            value: "help_only",
            label: "With help",
            image: ARM_MOVEMENT_HELP,
            imageLabel: "Person moving one arm with support from another person",
          },
          {
            value: "no_movement",
            label: "No movement",
            image: ARM_MOVEMENT_NONE,
            imageLabel: "Person seated with both arms resting still",
          },
        ] as const;
        const additionalChoices = [
          {
            value: "not_affected",
            label: "My arm was not affected",
            image: ARM_MOVEMENT_UNAFFECTED,
            imageLabel: "Person smiling and giving two thumbs up",
          },
          {
            value: "not_sure",
            label: "I am not sure",
            image: ARM_MOVEMENT_UNSURE,
            imageLabel: "Person thinking with one hand under their chin",
          },
        ] as const;

        const renderMovementChoice = (choice: typeof movementChoices[number]) => {
          const active = selectedMovement === choice.value;
          return (
            <Pressable
              key={choice.value}
              testID={`onb-opt-affected_arm_movement-${choice.value}`}
              accessibilityRole="radio"
              accessibilityState={{ selected: active }}
              accessibilityLabel={choice.label}
              onPress={() => setVal("affected_arm_movement", choice.value)}
              style={({ pressed }) => [
                styles.armMovementChoice,
                useWideArmMovementLayout && styles.armMovementChoiceWide,
                pressed && styles.armMovementChoicePressed,
              ]}
            >
              <View style={[
                styles.armMovementPictureHalo,
                useWideArmMovementLayout && styles.armMovementPictureHaloWide,
                active && styles.armMovementPictureHaloActive,
              ]}>
                <View style={[
                  styles.armMovementPicture,
                  useWideArmMovementLayout && styles.armMovementPictureWide,
                  active && styles.armMovementPictureActive,
                ]}>
                  <Image
                    source={choice.image}
                    resizeMode="contain"
                    accessibilityLabel={choice.imageLabel}
                    style={styles.armMovementImage}
                  />
                </View>
                {active ? (
                  <View style={styles.armMovementCheck}>
                    <Ionicons name="checkmark" size={31} color={colors.onBrandPrimary} />
                  </View>
                ) : null}
              </View>
              <Text style={[styles.armMovementChoiceLabel, active && styles.armMovementChoiceLabelActive]}>{choice.label}</Text>
            </Pressable>
          );
        };

        return (
          <View
            testID="affected-arm-movement-selector"
            accessibilityRole="radiogroup"
            style={styles.armMovementLayout}
          >
            <Text style={[styles.armMovementPrompt, useWideArmMovementLayout && styles.armMovementPromptWide]}>
              Which picture is closest to you?
            </Text>

            {!useWideArmMovementLayout ? (
              <View style={styles.armMovementDirectionRow}>
                <Ionicons name="arrow-back" size={27} color={colors.brandPrimary} />
                <Text style={styles.armMovementDirectionText}>More movement</Text>
                <View style={styles.armMovementDirectionLine} />
                <Text style={styles.armMovementDirectionText}>Less movement</Text>
                <Ionicons name="arrow-forward" size={27} color={colors.brandPrimary} />
              </View>
            ) : null}

            <View style={[styles.armMovementSpectrum, useWideArmMovementLayout && styles.armMovementSpectrumWide]}>
              {useWideArmMovementLayout ? (
                <View style={styles.armMovementEndLabel}>
                  <Text style={styles.armMovementEndLabelText}>More{"\n"}movement</Text>
                  <Ionicons name="arrow-back" size={38} color={colors.brandPrimary} />
                </View>
              ) : null}
              <View style={[styles.armMovementTrackArea, useWideArmMovementLayout && styles.armMovementTrackAreaWide]}>
                {useWideArmMovementLayout ? <View pointerEvents="none" style={styles.armMovementTrack} /> : null}
                <View style={[styles.armMovementChoices, useWideArmMovementLayout && styles.armMovementChoicesWide]}>
                  {movementChoices.map(renderMovementChoice)}
                </View>
              </View>
              {useWideArmMovementLayout ? (
                <View style={styles.armMovementEndLabel}>
                  <Ionicons name="arrow-forward" size={38} color={colors.brandPrimary} />
                  <Text style={styles.armMovementEndLabelText}>Less{"\n"}movement</Text>
                </View>
              ) : null}
            </View>

            <View style={[styles.armMovementAdditionalChoices, useWideArmMovementLayout && styles.armMovementAdditionalChoicesWide]}>
              {additionalChoices.map((choice) => {
                const active = selectedMovement === choice.value;
                return (
                  <Pressable
                    key={choice.value}
                    testID={`onb-opt-affected_arm_movement-${choice.value}`}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: active }}
                    accessibilityLabel={choice.label}
                    onPress={() => setVal("affected_arm_movement", choice.value)}
                    style={({ pressed }) => [
                      styles.armMovementAdditionalChoice,
                      useWideArmMovementLayout && styles.armMovementAdditionalChoiceWide,
                      active && styles.armMovementAdditionalChoiceActive,
                      pressed && styles.armMovementChoicePressed,
                    ]}
                  >
                    <Image
                      source={choice.image}
                      resizeMode="contain"
                      accessibilityLabel={choice.imageLabel}
                      style={[
                        styles.armMovementAdditionalImage,
                        useWideArmMovementLayout && styles.armMovementAdditionalImageWide,
                      ]}
                    />
                    <Text style={[
                      styles.armMovementAdditionalLabel,
                      useWideArmMovementLayout && styles.armMovementAdditionalLabelWide,
                      active && styles.armMovementChoiceLabelActive,
                    ]}>{choice.label}</Text>
                    <View style={[
                      styles.armMovementAdditionalIndicator,
                      useWideArmMovementLayout && styles.armMovementAdditionalIndicatorWide,
                      active && styles.armMovementAdditionalIndicatorActive,
                    ]}>
                      {active ? (
                        <Ionicons name="checkmark" size={29} color={colors.onBrandPrimary} />
                      ) : choice.value === "not_sure" ? (
                        <Ionicons name="help" size={28} color={colors.brandPrimary} />
                      ) : null}
                    </View>
                  </Pressable>
                );
              })}
            </View>
          </View>
        );
      }

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

      if (step.key === "affected_areas") {
        const anatomy = getAgeAnatomyPresentation(typeof values.age_band === "string" ? values.age_band : null);
        const toggleAffectedArea = (value: string) => {
          const active = selected.includes(value);
          if (value === "other") {
            if (active) {
              setVal(step.key, selected.filter((item) => item !== "other"));
              setVal("affected_areas_other", undefined);
              setOtherAreaText("");
            } else {
              setShowOtherArea(true);
            }
            return;
          }
          if (value === "unsure") {
            setVal(step.key, active ? [] : ["unsure"]);
            setVal("affected_areas_other", undefined);
            setOtherAreaText("");
            return;
          }
          const next = active
            ? selected.filter((item) => item !== value)
            : [...selected.filter((item) => item !== "unsure"), value];
          setVal(step.key, next);
        };
        const selectedLabels = step.options!
          .filter((option) => selected.includes(option.value))
          .map((option) => option.value === "other" && values.affected_areas_other
            ? String(values.affected_areas_other)
            : option.label.replace(" (shoulder, arm or hand)", "").replace(" (hip, leg or foot)", ""));
        const limbOptions = [
          { value: "left_upper", side: "L", label: "Your left arm" },
          { value: "right_upper", side: "R", label: "Your right arm" },
          { value: "left_lower", side: "L", label: "Your left leg" },
          { value: "right_lower", side: "R", label: "Your right leg" },
        ];

        const renderLimbChoice = (option: typeof limbOptions[number]) => {
          const active = selected.includes(option.value);
          return (
            <Pressable
              key={option.value}
              testID={`onb-multi-affected_areas-${option.value}`}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: active }}
              onPress={() => toggleAffectedArea(option.value)}
              style={[styles.bodyAreaChoice, useWideAffectedAreaLayout && styles.bodyAreaChoiceWide, active && styles.bodyAreaChoiceActive]}
            >
              <View style={[styles.sideBadge, active && styles.sideBadgeActive]}>
                <Text style={[styles.sideBadgeText, active && styles.sideBadgeTextActive]}>{option.side}</Text>
              </View>
              <Text style={[styles.bodyAreaChoiceText, active && styles.bodyAreaChoiceTextActive]}>{option.label}</Text>
              <Ionicons
                name={active ? "checkmark-circle" : "ellipse-outline"}
                size={25}
                color={active ? colors.brandPrimary : colors.borderStrong}
              />
            </Pressable>
          );
        };

        const additionalOptions = [
          { value: "face_speech", label: "Face or speech", icon: "account-voice" as const },
          { value: "other", label: "Another area", icon: "human" as const },
          { value: "unsure", label: "Not sure yet", icon: "help-circle-outline" as const },
        ];

        return (
          <View style={[styles.bodyAreaLayout, useWideAffectedAreaLayout && styles.bodyAreaLayoutWide]} testID="affected-area-selector">
            <View style={[styles.bodyAreaMain, useWideAffectedAreaLayout && styles.bodyAreaMainWide]}>
              {useWideAffectedAreaLayout ? (
                <View style={styles.limbColumn}>
                  {renderLimbChoice(limbOptions[0])}
                  {renderLimbChoice(limbOptions[2])}
                </View>
              ) : null}

              <View style={styles.anatomyPanel}>
                <Image source={anatomy.source} resizeMode="contain" accessibilityLabel={anatomy.viewLabel} style={[styles.bodyAreaAnatomy, useWideAffectedAreaLayout && styles.bodyAreaAnatomyWide]} />
                <Text style={styles.anatomyPrompt}>Choose every area that was affected</Text>
              </View>

              {useWideAffectedAreaLayout ? (
                <View style={styles.limbColumn}>
                  {renderLimbChoice(limbOptions[1])}
                  {renderLimbChoice(limbOptions[3])}
                </View>
              ) : (
                <View style={styles.limbGrid}>{limbOptions.map(renderLimbChoice)}</View>
              )}
            </View>

            <View style={[styles.additionalAreaColumn, useWideAffectedAreaLayout && styles.additionalAreaColumnWide]}>
              {additionalOptions.map((option) => {
                const active = selected.includes(option.value);
                return (
                  <Pressable
                    key={option.value}
                    testID={`onb-multi-affected_areas-${option.value}`}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: active }}
                    onPress={() => toggleAffectedArea(option.value)}
                    style={[styles.additionalAreaChoice, active && styles.bodyAreaChoiceActive]}
                  >
                    <View style={[styles.additionalAreaIcon, active && styles.additionalAreaIconActive]}>
                      <MaterialCommunityIcons name={option.icon} size={34} color={active ? colors.brandPrimary : colors.onSurfaceTertiary} />
                    </View>
                    <View style={styles.additionalAreaCopy}>
                      <Text style={[styles.additionalAreaLabel, active && styles.bodyAreaChoiceTextActive]}>{option.label}</Text>
                      {option.value === "other" && active && values.affected_areas_other ? (
                        <Text numberOfLines={2} style={styles.additionalAreaDetail}>{String(values.affected_areas_other)}</Text>
                      ) : null}
                    </View>
                    <Ionicons name={active ? "checkmark-circle" : "ellipse-outline"} size={25} color={active ? colors.brandPrimary : colors.borderStrong} />
                  </Pressable>
                );
              })}
            </View>

            {selectedLabels.length > 0 ? (
              <View style={styles.bodyAreaSummary} testID="affected-area-summary">
                <Ionicons name="checkmark-circle" size={23} color={colors.success} />
                <Text style={styles.bodyAreaSummaryText}>{selectedLabels.join(" · ")}</Text>
              </View>
            ) : null}
          </View>
        );
      }

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
                  const isExclusiveAnswer = ["none", "not_sure", "unsure"].includes(o.value);
                  if (isExclusiveAnswer) {
                    next = active ? [] : ["none"];
                    if (o.value !== "none") next = active ? [] : [o.value];
                    if (step.key === "medical_conditions") {
                      setVal("medical_conditions_other", undefined);
                      setOtherConditionText("");
                    }
                  }
                  else next = active
                    ? selected.filter((s) => s !== o.value)
                    : [...selected.filter((s) => !["none", "not_sure", "unsure"].includes(s)), o.value];
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
        <Pressable
          testID="onb-back"
          accessibilityLabel={idx > 0 ? "Previous question" : "Leave without changing your answers"}
          onPress={() => idx > 0 ? setIdx(idx - 1) : startsFromSavedProfile ? router.back() : undefined}
          disabled={idx === 0 && !startsFromSavedProfile}
          hitSlop={12}
        >
          <Ionicons name="chevron-back" size={26} color={idx === 0 && !startsFromSavedProfile ? colors.onSurfaceTertiary : colors.onSurface} />
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
          <Text style={[
            styles.question,
            step.key === "affected_areas" && useWideAffectedAreaLayout && styles.bodyAreaQuestion,
            step.key === "dominant_hand" && useWideDominantHandLayout && styles.dominantHandQuestionWide,
            step.key === "sitting_ability" && useWideSittingAbilityLayout && styles.sittingAbilityQuestionWide,
            step.key === "affected_arm_movement" && useWideArmMovementLayout && styles.armMovementQuestionWide,
          ]} testID={`onb-q-${step.key}`}>{step.question}</Text>
          {step.helper && <Text style={[
            styles.helper,
            step.key === "affected_areas" && useWideAffectedAreaLayout && styles.bodyAreaHelper,
            step.key === "dominant_hand" && useWideDominantHandLayout && styles.dominantHandHelperWide,
            step.key === "sitting_ability" && useWideSittingAbilityLayout && styles.sittingAbilityHelperWide,
            step.key === "affected_arm_movement" && useWideArmMovementLayout && styles.armMovementHelperWide,
          ]}>{step.helper}</Text>}
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
  dominantHandLayout: { width: "100%", gap: spacing.md },
  dominantHandLayoutWide: { flexDirection: "row", alignItems: "stretch", gap: spacing.lg },
  dominantPersonCard: { minWidth: 0, alignItems: "center", paddingHorizontal: spacing.sm, paddingTop: spacing.md, paddingBottom: spacing.sm, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  dominantPersonCardWide: { flex: 1.65, minHeight: 430, paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  dominantDirectionNote: { color: colors.brandPrimary, fontSize: 15, lineHeight: 20, fontWeight: "800", textAlign: "center" },
  dominantPersonRow: { width: "100%", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  dominantPersonImage: { flexShrink: 1, width: 132, height: 224 },
  dominantPersonImageWide: { width: 225, height: 340 },
  dominantSideChoice: { flexShrink: 0, width: 82, aspectRatio: 1, alignItems: "center", justifyContent: "center", gap: 1, borderRadius: 999, borderWidth: 3, borderColor: colors.borderStrong, backgroundColor: colors.surface },
  dominantSideChoiceWide: { width: 116, borderWidth: 4, gap: spacing.xs },
  dominantSideChoiceActive: { borderColor: colors.brandPrimary, backgroundColor: "#EEF6F0" },
  dominantSideLabel: { color: colors.onSurface, fontSize: 14, lineHeight: 18, fontWeight: "900" },
  dominantSideLabelActive: { color: colors.brandPrimary },
  dominantSelectionSummary: { minHeight: 28, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs },
  dominantSelectionSummaryText: { color: colors.brandPrimary, fontSize: 16, lineHeight: 22, fontWeight: "800", textAlign: "center" },
  dominantSelectionHint: { color: colors.onSurfaceTertiary, fontSize: 13, lineHeight: 20, fontWeight: "600", textAlign: "center" },
  dominantBothCard: { minWidth: 0, minHeight: 140, flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.sm, borderWidth: 2, borderColor: colors.border, backgroundColor: colors.surface },
  dominantBothCardWide: { flex: 1, minHeight: 430, flexDirection: "column", alignItems: "stretch", justifyContent: "center", paddingHorizontal: spacing.xl, paddingVertical: spacing.lg },
  dominantChoiceActive: { borderColor: colors.brandPrimary, backgroundColor: "#EEF6F0" },
  dominantHandsImage: { flexShrink: 0, width: 120, height: 104 },
  dominantHandsImageWide: { width: "100%", height: 220 },
  dominantBothCopy: { flex: 1, minWidth: 0, justifyContent: "center", gap: 4 },
  dominantBothTitleRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  dominantBothEyebrow: { color: colors.onSurface, fontSize: 16, lineHeight: 21, fontWeight: "900" },
  dominantBothTitle: { color: colors.onSurface, fontSize: 19, lineHeight: 25, fontWeight: "800" },
  dominantBothDescription: { color: colors.onSurfaceSecondary, fontSize: 14, lineHeight: 20, fontWeight: "600" },
  dominantHandQuestionWide: { fontSize: 32, lineHeight: 39 },
  dominantHandHelperWide: { fontSize: 17, lineHeight: 24 },
  sittingAbilityLayout: { width: "100%", gap: spacing.md },
  sittingChoiceGrid: { width: "100%", gap: spacing.sm },
  sittingChoiceGridWide: { flexDirection: "row", alignItems: "stretch", gap: spacing.md },
  sittingChoiceCard: { width: "100%", minHeight: 148, flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.sm, borderWidth: 2, borderColor: colors.borderStrong, backgroundColor: colors.surface },
  sittingChoiceCardWide: { flex: 1, width: "auto", minWidth: 0, minHeight: 360, flexDirection: "column", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  sittingChoiceCardActive: { borderColor: colors.brandPrimary, borderWidth: 3, backgroundColor: "#EEF6F0" },
  sittingChoiceImage: { flexShrink: 0, width: 116, height: 116 },
  sittingChoiceImageWide: { width: "100%", height: 235 },
  sittingChoiceLabel: { flex: 1, minWidth: 0, color: colors.onSurface, fontSize: 17, lineHeight: 23, fontWeight: "800" },
  sittingChoiceLabelWide: { flex: 0, minHeight: 48, textAlign: "center", fontSize: 18, lineHeight: 24 },
  sittingChoiceIndicator: { flexShrink: 0, width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center", borderWidth: 3, borderColor: colors.brandPrimary, backgroundColor: colors.surface },
  sittingChoiceIndicatorActive: { backgroundColor: colors.brandPrimary },
  sittingUnsureChoice: { width: "100%", minHeight: 86, flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: radius.sm, borderWidth: 2, borderColor: colors.borderStrong, backgroundColor: colors.surface },
  sittingUnsureImage: { flexShrink: 0, width: 92, height: 68 },
  sittingUnsureLabel: { flex: 1, minWidth: 0, color: colors.onSurface, fontSize: 18, lineHeight: 24, fontWeight: "800" },
  sittingAbilityQuestionWide: { fontSize: 34, lineHeight: 42 },
  sittingAbilityHelperWide: { fontSize: 18, lineHeight: 25 },
  armMovementLayout: { width: "100%", alignItems: "center", gap: spacing.lg },
  armMovementPrompt: { color: colors.brandPrimary, fontSize: 23, lineHeight: 30, fontWeight: "900", textAlign: "center" },
  armMovementPromptWide: { fontSize: 30, lineHeight: 38 },
  armMovementDirectionRow: { width: "100%", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs, paddingHorizontal: spacing.xs },
  armMovementDirectionText: { color: colors.brandPrimary, fontSize: 13, lineHeight: 18, fontWeight: "900", textAlign: "center" },
  armMovementDirectionLine: { flex: 1, height: 3, borderRadius: 2, backgroundColor: colors.brandPrimary },
  armMovementSpectrum: { width: "100%" },
  armMovementSpectrumWide: { minHeight: 320, flexDirection: "row", alignItems: "center", justifyContent: "center" },
  armMovementEndLabel: { width: 122, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs },
  armMovementEndLabelText: { color: colors.brandPrimary, fontSize: 18, lineHeight: 24, fontWeight: "900", textAlign: "center" },
  armMovementTrackArea: { width: "100%" },
  armMovementTrackAreaWide: { flex: 1, width: "auto", position: "relative", justifyContent: "center" },
  armMovementTrack: { position: "absolute", left: 92, right: 92, top: 126, height: 6, borderRadius: 3, backgroundColor: colors.brandPrimary },
  armMovementChoices: { width: "100%", flexDirection: "row", flexWrap: "wrap", justifyContent: "center", alignItems: "flex-start", gap: spacing.md },
  armMovementChoicesWide: { flexWrap: "nowrap", justifyContent: "space-between", gap: spacing.sm },
  armMovementChoice: { width: "46%", minWidth: 142, maxWidth: 210, alignItems: "center", gap: spacing.sm },
  armMovementChoiceWide: { flex: 1, width: "auto", minWidth: 0, maxWidth: 240 },
  armMovementChoicePressed: { opacity: 0.78 },
  armMovementPictureHalo: { width: 164, height: 164, borderRadius: 82, alignItems: "center", justifyContent: "center", backgroundColor: "transparent", position: "relative" },
  armMovementPictureHaloWide: { width: 244, height: 244, borderRadius: 122 },
  armMovementPictureHaloActive: { backgroundColor: "rgba(74, 120, 86, 0.14)" },
  armMovementPicture: { width: 148, height: 148, borderRadius: 74, overflow: "hidden", borderWidth: 3, borderColor: colors.brandPrimary, backgroundColor: colors.surface },
  armMovementPictureWide: { width: 224, height: 224, borderRadius: 112 },
  armMovementPictureActive: { borderWidth: 5, borderColor: "#235E34" },
  armMovementImage: { width: "100%", height: "100%" },
  armMovementCheck: { position: "absolute", top: 1, right: 1, width: 49, height: 49, borderRadius: 25, alignItems: "center", justifyContent: "center", backgroundColor: "#246536", borderWidth: 3, borderColor: colors.surface },
  armMovementChoiceLabel: { minHeight: 48, color: colors.onSurface, fontSize: 17, lineHeight: 23, fontWeight: "900", textAlign: "center" },
  armMovementChoiceLabelActive: { color: colors.brandPrimary },
  armMovementAdditionalChoices: { width: "100%", gap: spacing.sm },
  armMovementAdditionalChoicesWide: { flexDirection: "row", alignItems: "stretch", gap: spacing.md },
  armMovementAdditionalChoice: { width: "100%", minHeight: 112, flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.md, borderWidth: 2, borderColor: colors.border, backgroundColor: "#F7F9F6" },
  armMovementAdditionalChoiceWide: { flex: 1, width: "auto", minWidth: 0, minHeight: 146, paddingHorizontal: spacing.xl },
  armMovementAdditionalChoiceActive: { borderColor: colors.brandPrimary, backgroundColor: "#EEF6F0" },
  armMovementAdditionalImage: { flexShrink: 0, width: 80, height: 80 },
  armMovementAdditionalImageWide: { width: 122, height: 122 },
  armMovementAdditionalLabel: { flex: 1, minWidth: 0, color: colors.onSurface, fontSize: 17, lineHeight: 23, fontWeight: "900", textAlign: "center" },
  armMovementAdditionalLabelWide: { fontSize: 21, lineHeight: 28 },
  armMovementAdditionalIndicator: { flexShrink: 0, width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.brandPrimary, backgroundColor: colors.surface },
  armMovementAdditionalIndicatorWide: { width: 52, height: 52, borderRadius: 26 },
  armMovementAdditionalIndicatorActive: { backgroundColor: colors.brandPrimary },
  armMovementQuestionWide: { fontSize: 34, lineHeight: 42 },
  armMovementHelperWide: { fontSize: 18, lineHeight: 25 },
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
  bodyAreaLayout: { width: "100%", gap: spacing.md },
  bodyAreaLayoutWide: { flexDirection: "row", flexWrap: "wrap", alignItems: "stretch", gap: spacing.lg },
  bodyAreaMain: { flex: 1, minWidth: 0, gap: spacing.md },
  bodyAreaMainWide: { minWidth: 760, flexDirection: "row", alignItems: "center", justifyContent: "center" },
  limbColumn: { width: 240, gap: spacing.xl, justifyContent: "space-around" },
  limbGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  anatomyPanel: { minWidth: 0, alignItems: "center", justifyContent: "center" },
  bodyAreaAnatomy: { width: 170, height: 300 },
  bodyAreaAnatomyWide: { width: 225, height: 400 },
  anatomyPrompt: { maxWidth: 230, color: colors.onSurfaceSecondary, fontSize: 13, lineHeight: 18, fontWeight: "700", textAlign: "center", marginTop: spacing.xs },
  bodyAreaChoice: { flex: 1, minWidth: 230, minHeight: 78, flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.sm, borderWidth: 2, borderColor: colors.borderStrong, backgroundColor: colors.surface },
  bodyAreaChoiceWide: { flex: 0, width: "100%", minWidth: 0 },
  bodyAreaChoiceActive: { borderColor: colors.brandPrimary, backgroundColor: "#EEF6F0" },
  sideBadge: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  sideBadgeActive: { backgroundColor: colors.brandPrimary },
  sideBadgeText: { color: colors.onSurfaceSecondary, fontSize: 17, fontWeight: "900" },
  sideBadgeTextActive: { color: colors.onBrandPrimary },
  bodyAreaChoiceText: { flex: 1, color: colors.onSurface, fontSize: 15, lineHeight: 20, fontWeight: "800", textTransform: "uppercase" },
  bodyAreaChoiceTextActive: { color: colors.brandPrimary },
  additionalAreaColumn: { gap: spacing.sm },
  additionalAreaColumnWide: { width: 310 },
  additionalAreaChoice: { minHeight: 96, flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.sm, borderWidth: 2, borderColor: colors.borderStrong, backgroundColor: colors.surface },
  additionalAreaIcon: { width: 58, height: 58, borderRadius: 29, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary },
  additionalAreaIconActive: { backgroundColor: colors.brandTertiary },
  additionalAreaCopy: { flex: 1, minWidth: 0 },
  additionalAreaLabel: { color: colors.onSurface, fontSize: 17, lineHeight: 22, fontWeight: "800" },
  additionalAreaDetail: { color: colors.onSurfaceSecondary, fontSize: 12, lineHeight: 17, marginTop: 3 },
  bodyAreaSummary: { width: "100%", minHeight: 48, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.sm, backgroundColor: "#EEF6F0" },
  bodyAreaSummaryText: { flexShrink: 1, color: colors.brandPrimary, fontSize: 14, lineHeight: 20, fontWeight: "800", textAlign: "center" },
  bodyAreaQuestion: { fontSize: 34, lineHeight: 42 },
  bodyAreaHelper: { fontSize: 18, lineHeight: 25 },
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
