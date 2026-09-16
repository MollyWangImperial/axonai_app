import { useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { discoveryQuestions, getDiscoveryResult, type DiscoveryAnswers } from "@/src/landingDiscovery";

type Props = { onSignUp: (focus: string) => void; onSignIn: () => void };
const GREEN = "#004A38";
const INK = "#083547";

export default function LandingDiscoverySurvey({ onSignUp, onSignIn }: Props) {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<DiscoveryAnswers>({});
  const scroll = useRef<ScrollView>(null);
  const { width } = useWindowDimensions();
  const compact = width < 600;
  const question = discoveryQuestions[step];
  const result = step === discoveryQuestions.length ? getDiscoveryResult(answers) : null;
  const goTo = (next: number) => {
    setStep(next);
    scroll.current?.scrollTo({ y: 0, animated: false });
  };

  return (
    <ScrollView ref={scroll} contentContainerStyle={[styles.content, compact && styles.compactContent]} keyboardShouldPersistTaps="handled">
      <Text style={styles.eyebrow}>{result ? "YOUR NEXT STEP" : "A MINUTE FOR YOUR MOVEMENT"}</Text>
      {result ? (
        <View testID="discovery-result">
          <Text accessibilityRole="header" accessibilityLiveRegion="polite" style={[styles.title, compact && styles.compactTitle]}>{result.title}</Text>
          <Text style={styles.description}>{result.introduction}</Text>
          <View style={styles.features}>
            {result.features.map((feature, index) => (
              <View key={feature.title} style={styles.feature}>
                <Ionicons name={index === 0 ? "body-outline" : index === 1 ? "search-outline" : "footsteps-outline"} size={24} color={GREEN} />
                <View style={styles.featureCopy}>
                  <Text style={styles.featureTitle}>{feature.title}</Text>
                  <Text style={styles.featureDetail}>{feature.detail}</Text>
                </View>
              </View>
            ))}
          </View>
          <Text style={styles.context}>This is an introduction to Rehyn based on your interests. Your health and movement assessment comes after sign-up.</Text>
          <Pressable testID="discovery-signup" accessibilityRole="button" onPress={() => onSignUp(result.focus)} style={({ pressed }) => [styles.primary, pressed && styles.pressed]}>
            <Text style={styles.primaryText}>Sign up to explore Rehyn</Text>
            <Ionicons name="arrow-forward" size={22} color="#FFFFFF" />
          </Pressable>
          <Text style={styles.accessNote}>A trial access code is required to create an account.</Text>
          <Pressable testID="discovery-back" accessibilityRole="button" onPress={() => goTo(discoveryQuestions.length - 1)} style={styles.textButton}>
            <Text style={styles.link}>Review my answers</Text>
          </Pressable>
        </View>
      ) : (
        <View testID={`discovery-question-${question.id}`}>
          <View style={styles.progressRow}>
            <Text style={styles.stepLabel}>Question {step + 1} of {discoveryQuestions.length}</Text>
            <Text style={styles.stepHint}>No camera needed</Text>
          </View>
          <View accessibilityRole="progressbar" accessibilityLabel="Survey progress" aria-valuemin={0} aria-valuemax={4} aria-valuenow={step + 1} style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${((step + 1) / discoveryQuestions.length) * 100}%` }]} />
          </View>
          <Text accessibilityRole="header" accessibilityLiveRegion="polite" style={[styles.title, compact && styles.compactTitle]}>{question.title}</Text>
          <Text style={styles.description}>{question.hint}</Text>
          <View accessibilityRole="radiogroup" accessibilityLabel={question.title} style={styles.options}>
            {question.options.map(option => {
              const selected = answers[question.id] === option.id;
              return (
                <Pressable
                  key={option.id}
                  testID={`discovery-option-${option.id}`}
                  accessibilityRole="radio"
                  aria-checked={selected}
                  onPress={() => setAnswers(current => ({ ...current, [question.id]: option.id }))}
                  style={({ pressed }) => [styles.option, selected && styles.selectedOption, pressed && styles.pressed]}
                >
                  <Text style={[styles.optionText, selected && styles.selectedOptionText]}>{option.label}</Text>
                  <Ionicons name={selected ? "checkmark-circle" : "ellipse-outline"} size={23} color={selected ? GREEN : "#899991"} />
                </Pressable>
              );
            })}
          </View>
          <View style={styles.navigation}>
            {step > 0 ? (
              <Pressable testID="discovery-back" accessibilityRole="button" onPress={() => goTo(step - 1)} style={styles.backButton}>
                <Ionicons name="arrow-back" size={20} color={GREEN} />
                <Text style={styles.link}>Back</Text>
              </Pressable>
            ) : null}
            <Pressable
              testID="discovery-next"
              accessibilityRole="button"
              disabled={!answers[question.id]}
              accessibilityState={{ disabled: !answers[question.id] }}
              onPress={() => goTo(step + 1)}
              style={({ pressed }) => [styles.primary, styles.nextButton, !answers[question.id] && styles.disabled, pressed && styles.pressed]}
            >
              <Text style={styles.primaryText}>{step === discoveryQuestions.length - 1 ? "See my next step" : "Continue"}</Text>
              <Ionicons name="arrow-forward" size={22} color="#FFFFFF" />
            </Pressable>
          </View>
        </View>
      )}
      <Pressable testID="discovery-signin" accessibilityRole="button" onPress={onSignIn} style={styles.textButton}>
        <Text style={styles.signInText}>Already have an account? <Text style={styles.link}>Sign in</Text></Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 36, paddingTop: 34, paddingBottom: 26 },
  compactContent: { paddingHorizontal: 22, paddingTop: 30, paddingBottom: 22 },
  eyebrow: { color: GREEN, fontSize: 12, fontWeight: "800", letterSpacing: 1.3, paddingRight: 42, marginBottom: 28 },
  progressRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10, marginBottom: 10 },
  stepLabel: { color: GREEN, fontSize: 14, fontWeight: "700" },
  stepHint: { color: "#66756F", fontSize: 13 },
  progressTrack: { height: 5, borderRadius: 3, backgroundColor: "#E3ECE7", overflow: "hidden", marginBottom: 26 },
  progressFill: { height: "100%", borderRadius: 3, backgroundColor: GREEN },
  title: { color: INK, fontSize: 32, lineHeight: 39, fontWeight: "700", letterSpacing: -0.7, marginBottom: 12 },
  compactTitle: { fontSize: 27, lineHeight: 33 },
  description: { color: "#536760", fontSize: 17, lineHeight: 25, marginBottom: 24 },
  options: { gap: 11 },
  option: { minHeight: 66, borderWidth: 1, borderColor: "#CCD9D1", borderRadius: 13, paddingVertical: 16, paddingHorizontal: 18, flexDirection: "row", alignItems: "center", gap: 14, backgroundColor: "#FFFFFF" },
  selectedOption: { borderColor: GREEN, backgroundColor: "#EDF5EF" },
  optionText: { flex: 1, color: INK, fontSize: 17, lineHeight: 24 },
  selectedOptionText: { color: GREEN, fontWeight: "600" },
  navigation: { flexDirection: "row", alignItems: "center", gap: 14, marginTop: 26 },
  primary: { minHeight: 58, backgroundColor: GREEN, borderRadius: 12, paddingHorizontal: 18, paddingVertical: 14, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10 },
  primaryText: { flexShrink: 1, textAlign: "center", color: "#FFFFFF", fontSize: 17, lineHeight: 23, fontWeight: "700" },
  nextButton: { flex: 1 },
  backButton: { minHeight: 48, flexDirection: "row", alignItems: "center", gap: 6, paddingRight: 6 },
  link: { color: GREEN, fontSize: 15, fontWeight: "700", textDecorationLine: "underline" },
  textButton: { minHeight: 48, alignItems: "center", justifyContent: "center", marginTop: 10 },
  signInText: { color: "#66756F", fontSize: 14, lineHeight: 21, textAlign: "center" },
  features: { borderRadius: 16, backgroundColor: "#F2F6F2", padding: 20, gap: 22, marginBottom: 20 },
  feature: { flexDirection: "row", alignItems: "flex-start", gap: 14 },
  featureCopy: { flex: 1 },
  featureTitle: { color: GREEN, fontSize: 18, lineHeight: 24, fontWeight: "700", marginBottom: 5 },
  featureDetail: { color: "#536760", fontSize: 15, lineHeight: 23 },
  context: { color: "#66756F", fontSize: 14, lineHeight: 21, marginBottom: 20 },
  accessNote: { color: "#66756F", fontSize: 13, lineHeight: 20, textAlign: "center", marginTop: 12 },
  disabled: { opacity: 0.42 },
  pressed: { opacity: 0.76 },
});
