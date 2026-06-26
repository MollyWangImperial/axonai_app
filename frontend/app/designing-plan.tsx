import { useEffect, useRef } from "react";
import { View, Text, StyleSheet, Animated, Easing } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { colors, spacing } from "@/src/theme";

export default function DesigningPlanScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const rotate = useRef(new Animated.Value(0)).current;
  const fadeIn = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.loop(
      Animated.timing(rotate, { toValue: 1, duration: 2400, useNativeDriver: true, easing: Easing.linear })
    ).start();
    Animated.timing(fadeIn, { toValue: 1, duration: 600, useNativeDriver: true }).start();
    const t = setTimeout(() => {
      if (id) router.replace({ pathname: "/rehab-plan", params: { id } });
      else router.replace("/");
    }, 2800);
    return () => clearTimeout(t);
  }, [id]);

  const spin = rotate.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] });

  return (
    <LinearGradient colors={[colors.brandPrimary, "#1C201D"]} style={styles.container}>
      <Animated.View style={[styles.ring, { transform: [{ rotate: spin }] }]}>
        <View style={[styles.dot, styles.d1]} />
        <View style={[styles.dot, styles.d2]} />
        <View style={[styles.dot, styles.d3]} />
      </Animated.View>

      <Animated.View style={{ opacity: fadeIn, alignItems: "center" }}>
        <View style={styles.iconWrap}>
          <Ionicons name="medical" size={32} color="#fff" />
        </View>
        <Text style={styles.title}>Designing your rehab plan</Text>
        <Text style={styles.sub}>Reviewing your assessment, matching to evidence-based exercises…</Text>
        <View style={styles.steps}>
          {[
            "Analyzing your movement",
            "Identifying focus areas",
            "Selecting exercises from Fugl-Meyer, CIMT & ARAT",
            "Personalizing your sets and reps",
          ].map((s, i) => (
            <View key={i} style={styles.step}>
              <Ionicons name="checkmark-circle" size={16} color={colors.brandTertiary} />
              <Text style={styles.stepText}>{s}</Text>
            </View>
          ))}
        </View>
      </Animated.View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg },
  ring: { width: 200, height: 200, position: "absolute", top: "20%" },
  dot: { width: 14, height: 14, borderRadius: 7, position: "absolute" },
  d1: { backgroundColor: colors.brandSecondary, top: 0, left: "50%", marginLeft: -7 },
  d2: { backgroundColor: colors.brandTertiary, bottom: 0, left: 20 },
  d3: { backgroundColor: "#fff", bottom: 0, right: 20 },
  iconWrap: { width: 72, height: 72, borderRadius: 36, backgroundColor: "rgba(255,255,255,0.15)", alignItems: "center", justifyContent: "center", marginBottom: spacing.md },
  title: { fontSize: 24, fontWeight: "800", color: "#fff", textAlign: "center", marginBottom: spacing.sm },
  sub: { fontSize: 15, color: colors.brandTertiary, textAlign: "center", marginBottom: spacing.lg, paddingHorizontal: spacing.lg },
  steps: { gap: spacing.sm, alignItems: "flex-start" },
  step: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  stepText: { color: "#fff", fontSize: 14, fontWeight: "600", opacity: 0.9 },
});
