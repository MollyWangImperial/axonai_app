import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useDisplayPreferences } from "@/src/displayPreferences";
import { PATIENT_SURVEY_STEPS, type PatientSurveyStep } from "@/src/patientSurvey";
import { radius, spacing } from "@/src/theme";

const RESPONSE_LABELS: Record<PatientSurveyStep["type"], string> = {
  text: "Written answer",
  number: "Number of months",
  single: "Choose one",
  multi: "Choose all that apply",
};

export default function SurveyQuestionsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { palette, scale } = useDisplayPreferences();

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
});
