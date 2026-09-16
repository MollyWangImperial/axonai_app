import { useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { discoveryQuestions, getDiscoveryResult, type DiscoveryAnswers } from "@/src/landingDiscovery";

type Props = { onSignUp: (focus: string) => void };
const GREEN = "#004A38";
const INK = "#083547";
const RESULT_BENEFITS = [
  { label: "Understand your movement", icon: "search-outline" },
  { label: "Track changes over time", icon: "stats-chart-outline" },
  { label: "Follow spoken guidance", icon: "volume-high-outline" },
] as const;

export default function LandingDiscoverySurvey({ onSignUp }: Props) {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<DiscoveryAnswers>({});
  const scroll = useRef<ScrollView>(null);
  const { width } = useWindowDimensions();
  const compact = width < 1100;
  const question = discoveryQuestions[step];
  const result = step === discoveryQuestions.length ? getDiscoveryResult(answers) : null;
  const goTo = (next: number) => {
    setStep(next);
    scroll.current?.scrollTo({ y: 0, animated: false });
  };

  return (
    <ScrollView ref={scroll} contentContainerStyle={[styles.content, compact && styles.compactContent]} keyboardShouldPersistTaps="handled">
      {result ? (
        <View testID="discovery-result" style={[styles.result, compact && styles.compactResult]}>
          <Text
            accessibilityRole="header"
            accessibilityLiveRegion="polite"
            style={[styles.resultTitle, compact && styles.compactResultTitle]}
          >
            Start with a movement check
          </Text>
          <Text style={[styles.resultSubtitle, compact && styles.compactResultSubtitle]}>
            We’ll use it to shape your programme.
          </Text>

          <View style={[styles.resultBenefitsCard, compact && styles.compactResultBenefitsCard]}>
            {RESULT_BENEFITS.map((benefit, index) => (
              <View key={benefit.label}>
                <View style={[styles.resultBenefit, compact && styles.compactResultBenefit]}>
                  <View style={[styles.resultIcon, compact && styles.compactResultIcon]} accessible={false}>
                    <Ionicons name={benefit.icon} size={compact ? 39 : 49} color={GREEN} />
                  </View>
                  <Text style={[styles.resultBenefitText, compact && styles.compactResultBenefitText]}>{benefit.label}</Text>
                </View>
                {index < RESULT_BENEFITS.length - 1 ? <View style={[styles.resultBenefitDivider, compact && styles.compactResultBenefitDivider]} /> : null}
              </View>
            ))}
          </View>

          <View style={[styles.resultDivider, compact && styles.compactResultDivider]} />
          <Pressable testID="discovery-signup" accessibilityRole="button" onPress={() => onSignUp(result.focus)} style={({ pressed }) => [styles.resultPrimary, compact && styles.compactResultPrimary, pressed && styles.pressed]}>
            <Text style={[styles.resultPrimaryText, compact && styles.compactResultPrimaryText]}>Sign up to try Rehyn</Text>
            <Ionicons name="arrow-forward" size={compact ? 24 : 31} color="#FFFFFF" />
          </Pressable>
        </View>
      ) : (
        <View testID={`discovery-question-${question.id}`}>
          <Text style={[styles.stepLabel, compact && styles.compactStepLabel]}>{step + 1} of {discoveryQuestions.length}</Text>
          <View accessibilityRole="progressbar" accessibilityLabel="Survey progress" aria-valuemin={0} aria-valuemax={4} aria-valuenow={step + 1} style={[styles.progressTrack, compact && styles.compactProgressTrack]}>
            <View style={[styles.progressFill, { width: `${((step + 1) / discoveryQuestions.length) * 100}%` }]} />
          </View>
          <Text accessibilityRole="header" accessibilityLiveRegion="polite" style={[styles.title, compact && styles.compactTitle]}>{question.title}</Text>
          <Text style={[styles.description, compact && styles.compactDescription]}>{question.hint}</Text>
          <View accessibilityRole="radiogroup" accessibilityLabel={question.title} style={[styles.options, compact && styles.compactOptions]}>
            {question.options.map(option => {
              const selected = answers[question.id] === option.id;
              const isLast = option.id === question.options[question.options.length - 1]?.id;
              return (
                <Pressable
                  key={option.id}
                  testID={`discovery-option-${option.id}`}
                  accessibilityRole="radio"
                  aria-checked={selected}
                  onPress={() => setAnswers(current => ({ ...current, [question.id]: option.id }))}
                  style={({ pressed }) => [styles.option, compact && styles.compactOption, isLast && styles.lastOption, selected && styles.selectedOption, pressed && styles.pressed]}
                >
                  <Text style={[styles.optionText, compact && styles.compactOptionText, selected && styles.selectedOptionText]}>{option.label}</Text>
                  <Ionicons name={selected ? "checkmark-circle" : "ellipse-outline"} size={compact ? 28 : 39} color={selected ? GREEN : "#7F9990"} />
                </Pressable>
              );
            })}
          </View>
          <View style={[styles.navigation, compact && styles.compactNavigation]}>
            {step > 0 ? (
              <Pressable testID="discovery-back" accessibilityRole="button" onPress={() => goTo(step - 1)} style={styles.backButton}>
                <Ionicons name="arrow-back" size={compact ? 20 : 24} color={GREEN} />
                <Text style={styles.link}>Back</Text>
              </Pressable>
            ) : null}
            <Pressable
              testID="discovery-next"
              accessibilityRole="button"
              disabled={!answers[question.id]}
              accessibilityState={{ disabled: !answers[question.id] }}
              onPress={() => goTo(step + 1)}
              style={({ pressed }) => [styles.primary, compact && styles.compactPrimary, !answers[question.id] && styles.disabled, pressed && styles.pressed]}
            >
              <Text style={[styles.primaryText, compact && styles.compactPrimaryText]}>{step === discoveryQuestions.length - 1 ? "See my next step" : "Continue"}</Text>
              <Ionicons name="arrow-forward" size={compact ? 24 : 31} color="#FFFFFF" />
            </Pressable>
          </View>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { width: "100%", paddingHorizontal: 60, paddingTop: 112, paddingBottom: 72 },
  compactContent: { paddingHorizontal: 22, paddingTop: 78, paddingBottom: 30 },
  stepLabel: { color: GREEN, fontSize: 29, lineHeight: 36, fontWeight: "800" },
  compactStepLabel: { fontSize: 18, lineHeight: 24 },
  progressTrack: { height: 10, borderRadius: 5, backgroundColor: "#E2EAE7", overflow: "hidden", marginTop: 18, marginBottom: 70 },
  compactProgressTrack: { height: 7, borderRadius: 4, marginTop: 12, marginBottom: 34 },
  progressFill: { height: "100%", borderRadius: 3, backgroundColor: GREEN },
  title: { color: INK, fontSize: 58, lineHeight: 74, fontWeight: "700", letterSpacing: -1.8, marginBottom: 24 },
  compactTitle: { fontSize: 31, lineHeight: 38, letterSpacing: -0.8, marginBottom: 14 },
  description: { color: "#637B74", fontSize: 33, lineHeight: 43, marginBottom: 49 },
  compactDescription: { fontSize: 17, lineHeight: 25, marginBottom: 24 },
  options: { borderWidth: 1, borderColor: "#C9D8D3", borderRadius: 18, overflow: "hidden" },
  compactOptions: { borderRadius: 14 },
  option: { minHeight: 132, borderBottomWidth: 1, borderBottomColor: "#D5DFDC", paddingVertical: 24, paddingHorizontal: 38, flexDirection: "row", alignItems: "center", gap: 22, backgroundColor: "#FFFFFF" },
  compactOption: { minHeight: 78, paddingVertical: 15, paddingHorizontal: 18, gap: 14 },
  lastOption: { borderBottomWidth: 0 },
  selectedOption: { borderColor: GREEN, backgroundColor: "#EDF5EF" },
  optionText: { flex: 1, color: INK, fontSize: 30, lineHeight: 38 },
  compactOptionText: { fontSize: 17, lineHeight: 24 },
  selectedOptionText: { color: GREEN, fontWeight: "600" },
  navigation: { width: "100%", gap: 14, marginTop: 60 },
  compactNavigation: { marginTop: 26 },
  primary: { width: "100%", minHeight: 112, backgroundColor: GREEN, borderRadius: 20, paddingHorizontal: 28, paddingVertical: 20, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 18 },
  compactPrimary: { minHeight: 62, borderRadius: 13, paddingHorizontal: 18, paddingVertical: 14, gap: 10 },
  primaryText: { flexShrink: 1, textAlign: "center", color: "#FFFFFF", fontSize: 31, lineHeight: 39, fontWeight: "800" },
  compactPrimaryText: { fontSize: 18, lineHeight: 24 },
  backButton: { alignSelf: "flex-start", minHeight: 48, flexDirection: "row", alignItems: "center", gap: 8, paddingRight: 10 },
  link: { color: GREEN, fontSize: 16, fontWeight: "700", textDecorationLine: "underline" },
  textButton: { minHeight: 48, alignItems: "center", justifyContent: "center", marginTop: 10 },
  result: { width: "100%", maxWidth: 1120, alignSelf: "center", paddingTop: 42, paddingHorizontal: 10 },
  compactResult: { maxWidth: 640, paddingTop: 62, paddingHorizontal: 0 },
  resultTitle: { color: INK, fontSize: 80, lineHeight: 90, fontWeight: "800", letterSpacing: -2.5, marginBottom: 4 },
  compactResultTitle: { fontSize: 34, lineHeight: 41, letterSpacing: -1, marginBottom: 20, paddingRight: 45 },
  resultSubtitle: { color: "#657F77", fontSize: 39, lineHeight: 50, fontWeight: "600", marginBottom: 54 },
  compactResultSubtitle: { fontSize: 23, lineHeight: 31, marginBottom: 40, paddingRight: 28 },
  resultBenefitsCard: { width: "100%", borderWidth: 1, borderColor: "#D6E7E2", borderRadius: 26, backgroundColor: "#FFFFFF", overflow: "hidden", marginBottom: 96, shadowColor: "#76A797", shadowOpacity: 0.13, shadowRadius: 22, shadowOffset: { width: 0, height: 10 } },
  compactResultBenefitsCard: { borderRadius: 14, marginBottom: 96, shadowOpacity: 0.1, shadowRadius: 14, shadowOffset: { width: 0, height: 7 } },
  resultBenefit: { minHeight: 150, flexDirection: "row", alignItems: "center", gap: 36, paddingHorizontal: 40, paddingVertical: 26 },
  compactResultBenefit: { minHeight: 116, gap: 24, paddingHorizontal: 20, paddingVertical: 18 },
  resultIcon: { width: 96, height: 96, borderRadius: 48, backgroundColor: "#EAF7F1", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  compactResultIcon: { width: 78, height: 78, borderRadius: 39 },
  resultBenefitText: { flex: 1, color: INK, fontSize: 36, lineHeight: 45, fontWeight: "800", letterSpacing: -0.8 },
  compactResultBenefitText: { fontSize: 22, lineHeight: 28, letterSpacing: -0.4 },
  resultBenefitDivider: { height: 1, marginHorizontal: 40, backgroundColor: "#D6E7E2" },
  compactResultBenefitDivider: { marginHorizontal: 20 },
  resultDivider: { width: "100%", height: 1, backgroundColor: "#C8D7D2", marginBottom: 34 },
  compactResultDivider: { marginBottom: 22 },
  resultPrimary: { width: "100%", minHeight: 108, backgroundColor: GREEN, borderRadius: 18, paddingHorizontal: 28, paddingVertical: 20, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 20 },
  compactResultPrimary: { minHeight: 68, borderRadius: 18, paddingHorizontal: 18, paddingVertical: 14, gap: 10 },
  resultPrimaryText: { color: "#FFFFFF", fontSize: 31, lineHeight: 39, fontWeight: "800", textAlign: "center" },
  compactResultPrimaryText: { fontSize: 19, lineHeight: 25 },
  disabled: { opacity: 0.42 },
  pressed: { opacity: 0.76 },
});
