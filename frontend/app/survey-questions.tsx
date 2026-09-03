import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, type StyleProp, Text, View, type ViewStyle } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { type DisplayPalette, useDisplayPreferences } from "@/src/displayPreferences";
import { PATIENT_SURVEY_STEPS, type PatientSurveyStep } from "@/src/patientSurvey";
import { radius, spacing } from "@/src/theme";

const RESPONSE_LABELS: Record<PatientSurveyStep["type"], string> = {
  text: "Written answer",
  number: "Number of months",
  single: "Choose one",
  multi: "Choose all that apply",
};

function RefillSurveyButton({ testID, palette, scale, onPress, style }: { testID: string; palette: DisplayPalette; scale: number; onPress: () => void; style?: StyleProp<ViewStyle> }) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel="Re-fill the survey"
      accessibilityHint="Goes through every setup question again, starting from your saved answers"
      onPress={onPress}
      style={[styles.refillButton, { backgroundColor: palette.brand }, style]}
    >
      <Ionicons name="refresh" size={20} color={palette.onBrand} />
      <Text style={[styles.refillButtonText, { color: palette.onBrand, fontSize: 16 * scale, lineHeight: 21 * scale }]}>Re-fill the survey</Text>
    </Pressable>
  );
}

export default function SurveyQuestionsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { palette, scale } = useDisplayPreferences();
  // Runs the full setup survey again, pre-filled with the saved answers.
  // Nothing changes until the patient saves the last question.
  const openRefill = () => router.push("/onboarding?mode=refill" as never);

  return (
    <View style={[styles.container, { backgroundColor: palette.page }]}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm, backgroundColor: palette.surface, borderBottomColor: palette.border }]}>
        <Pressable testID="survey-questions-back" accessibilityLabel="Go back" onPress={() => router.back()} style={styles.headerButton}>
          <Ionicons name="chevron-back" size={25} color={palette.text} />
        </Pressable>
        <Text style={[styles.headerTitle, { color: palette.text, fontSize: 18 * scale }]}>Survey questions</Text>
        <View style={styles.headerButton} />
      </View>

      <ScrollView
        testID="survey-questions-list"
        showsVerticalScrollIndicator={false}
        contentContainerStyle={[styles.scroll, { paddingBottom: Math.max(insets.bottom, spacing.lg) + spacing.xl }]}
      >
        <View style={styles.page}>
          <View style={styles.intro}>
            <Text style={[styles.title, { color: palette.text, fontSize: 28 * scale, lineHeight: 35 * scale }]}>All setup questions</Text>
            <Text style={[styles.subtitle, { color: palette.muted, fontSize: 14 * scale, lineHeight: 21 * scale }]}>These are the {PATIENT_SURVEY_STEPS.length} questions in your Rehyn setup survey. This reference page does not change your saved answers.</Text>
          </View>

          <View testID="survey-questions-refill-card" style={[styles.questionCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={styles.questionHeading}>
              <View style={[styles.numberBadge, { backgroundColor: palette.soft }]}>
                <Ionicons name="refresh" size={20} color={palette.brand} />
              </View>
              <View style={styles.questionCopy}>
                <Text style={[styles.question, { color: palette.text, fontSize: 17 * scale, lineHeight: 23 * scale }]}>Has something changed?</Text>
                <Text style={[styles.refillText, { color: palette.muted, fontSize: 13 * scale, lineHeight: 19 * scale }]}>
                  Re-fill the survey to update your saved answers. You&apos;ll go through the {PATIENT_SURVEY_STEPS.length} questions again, each starting from your current answer, so you only change what&apos;s different. Nothing is saved until you tap Finish at the end.
                </Text>
              </View>
            </View>
            <View style={styles.refillActions}>
              <RefillSurveyButton testID="survey-questions-refill" palette={palette} scale={scale} onPress={openRefill} />
            </View>
          </View>

          {PATIENT_SURVEY_STEPS.map((step, index) => (
            <View
              key={step.key}
              testID={`survey-question-${step.key}`}
              style={[styles.questionCard, { backgroundColor: palette.surface, borderColor: palette.border }]}
            >
              <View style={styles.questionHeading}>
                <View style={[styles.numberBadge, { backgroundColor: palette.soft }]}>
                  <Text style={[styles.numberText, { color: palette.brand }]}>{String(index + 1).padStart(2, "0")}</Text>
                </View>
                <View style={styles.questionCopy}>
                  <Text style={[styles.question, { color: palette.text, fontSize: 17 * scale, lineHeight: 23 * scale }]}>{step.question}</Text>
                  <View style={styles.metaRow}>
                    <Text style={[styles.responseType, { color: palette.brand }]}>{RESPONSE_LABELS[step.type]}</Text>
                    {step.optional ? <Text style={[styles.optional, { color: palette.muted, borderColor: palette.border }]}>Optional</Text> : null}
                  </View>
                </View>
              </View>

              {step.helper ? <Text style={[styles.helper, { color: palette.muted, fontSize: 13 * scale, lineHeight: 19 * scale }]}>{step.helper}</Text> : null}

              {step.options ? (
                <View style={[styles.options, { borderTopColor: palette.border }]}>
                  {step.options.map((option) => (
                    <View key={option.value} style={styles.optionRow}>
                      <Ionicons name={step.type === "multi" ? "square-outline" : "ellipse-outline"} size={16} color={palette.brand} />
                      {option.emoji ? <Text style={styles.emoji}>{option.emoji}</Text> : null}
                      <Text style={[styles.optionText, { color: palette.text, fontSize: 13 * scale, lineHeight: 19 * scale }]}>{option.label}</Text>
                    </View>
                  ))}
                </View>
              ) : (
                <View style={[styles.answerPreview, { backgroundColor: palette.soft }]}>
                  <Ionicons name={step.type === "number" ? "calculator-outline" : "create-outline"} size={18} color={palette.brand} />
                  <Text style={[styles.answerPreviewText, { color: palette.muted }]}>{step.type === "number" ? "Enter an approximate number" : "Type your answer in your own words"}</Text>
                </View>
              )}
            </View>
          ))}

          <View testID="survey-questions-refill-footer" style={[styles.refillFooter, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <Text style={[styles.refillFooterText, { color: palette.text, fontSize: 15 * scale, lineHeight: 21 * scale }]}>Ready to update your answers?</Text>
            <RefillSurveyButton testID="survey-questions-refill-bottom" palette={palette} scale={scale} onPress={openRefill} style={styles.refillButtonCentered} />
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { minHeight: 58, paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  headerButton: { width: 42, height: 42, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontWeight: "800" },
  scroll: { paddingHorizontal: spacing.md, paddingTop: spacing.lg },
  page: { width: "100%", maxWidth: 780, alignSelf: "center", gap: spacing.md },
  intro: { marginBottom: spacing.xs },
  title: { fontWeight: "900" },
  subtitle: { maxWidth: 620, marginTop: spacing.xs },
  questionCard: { borderWidth: 1, borderRadius: radius.sm, padding: spacing.md },
  questionHeading: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  numberBadge: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center" },
  numberText: { fontSize: 12, fontWeight: "900" },
  questionCopy: { flex: 1, minWidth: 0 },
  question: { fontWeight: "800" },
  metaRow: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.xs, marginTop: 6 },
  responseType: { fontSize: 11, fontWeight: "800", textTransform: "uppercase" },
  optional: { fontSize: 11, fontWeight: "700", borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2 },
  helper: { marginTop: spacing.sm, marginLeft: 54 },
  options: { marginTop: spacing.sm, marginLeft: 54, paddingTop: spacing.sm, borderTopWidth: 1, gap: 9 },
  optionRow: { minHeight: 24, flexDirection: "row", alignItems: "center", gap: 8 },
  optionText: { flex: 1 },
  emoji: { fontSize: 16 },
  answerPreview: { minHeight: 44, marginTop: spacing.sm, marginLeft: 54, borderRadius: radius.sm, paddingHorizontal: spacing.sm, flexDirection: "row", alignItems: "center", gap: spacing.xs },
  answerPreviewText: { flex: 1, fontSize: 12, lineHeight: 17 },
  refillText: { marginTop: 6 },
  refillActions: { marginTop: spacing.sm, marginLeft: 54 },
  refillButton: { minHeight: 52, maxWidth: "100%", alignSelf: "flex-start", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: radius.pill },
  refillButtonText: { flexShrink: 1, fontWeight: "800" },
  refillButtonCentered: { alignSelf: "center" },
  refillFooter: { borderWidth: 1, borderRadius: radius.sm, padding: spacing.md, alignItems: "center", gap: spacing.sm },
  refillFooterText: { fontWeight: "700", textAlign: "center" },
});
