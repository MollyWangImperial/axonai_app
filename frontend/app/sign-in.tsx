import { useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { signIn } from "@/src/auth";

export default function SignInScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [role, setRole] = useState<"patient" | "therapist">("patient");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!email.trim() || !name.trim()) {
      setErr("Please enter your name and email.");
      return;
    }
    setLoading(true); setErr(null);
    try {
      const u = await signIn(email.trim(), name.trim(), role);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      if (u.role === "therapist") router.replace("/therapist");
      else router.replace("/");
    } catch (e) {
      setErr("Sign-in failed. Try again.");
    } finally { setLoading(false); }
  };

  return (
    <LinearGradient colors={[colors.brandPrimary, "#1C201D"]} style={[styles.container, { paddingTop: insets.top + spacing.lg }]}>
      <View style={styles.brand}>
        <Ionicons name="heart" size={32} color="#fff" />
        <Text style={styles.brandText}>NeuroMotion</Text>
      </View>
      <Text style={styles.title}>Welcome.</Text>
      <Text style={styles.sub}>Sign in to begin — or continue your recovery.</Text>

      <View style={styles.tabs}>
        <Pressable onPress={() => setRole("patient")} style={[styles.tab, role === "patient" && styles.tabActive]} testID="role-patient">
          <Ionicons name="person" size={18} color={role === "patient" ? colors.brandPrimary : "#fff"} />
          <Text style={[styles.tabText, role === "patient" && { color: colors.brandPrimary }]}>I'm a patient</Text>
        </Pressable>
        <Pressable onPress={() => setRole("therapist")} style={[styles.tab, role === "therapist" && styles.tabActive]} testID="role-therapist">
          <Ionicons name="medkit" size={18} color={role === "therapist" ? colors.brandPrimary : "#fff"} />
          <Text style={[styles.tabText, role === "therapist" && { color: colors.brandPrimary }]}>I'm a therapist</Text>
        </Pressable>
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <TextInput value={name} onChangeText={setName} placeholder="Your name" placeholderTextColor="#bcc2ba" style={styles.input} testID="signin-name" autoCapitalize="words" />
        <TextInput value={email} onChangeText={setEmail} placeholder="Email" placeholderTextColor="#bcc2ba" style={styles.input} keyboardType="email-address" autoCapitalize="none" testID="signin-email" />
        {err && <Text style={styles.err}>{err}</Text>}
        <Pressable onPress={submit} style={styles.submit} disabled={loading} testID="signin-submit">
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.submitText}>{role === "patient" ? "Continue" : "Open therapist portal"}</Text>}
        </Pressable>
        <Text style={styles.disclaim}>
          New here? Your patient account starts with <Text style={{ color: colors.brandSecondary, fontWeight: "800" }}>100 credits</Text> — enough for several assessments, a rehab plan, and guided exercise.
        </Text>
        <Text style={styles.mvp}>MVP sign-in uses email only (no password). Secure Google + password login coming soon.</Text>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: spacing.lg },
  brand: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: spacing.xl },
  brandText: { color: "#fff", fontWeight: "800", fontSize: 22, letterSpacing: 1 },
  title: { color: "#fff", fontSize: 32, fontWeight: "800", marginBottom: spacing.xs },
  sub: { color: colors.brandTertiary, fontSize: 15, marginBottom: spacing.lg },
  tabs: { flexDirection: "row", gap: spacing.sm, backgroundColor: "rgba(255,255,255,0.1)", padding: 4, borderRadius: radius.lg, marginBottom: spacing.md },
  tab: { flex: 1, flexDirection: "row", gap: 6, padding: 12, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  tabActive: { backgroundColor: "#fff" },
  tabText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  input: { backgroundColor: "rgba(255,255,255,0.12)", color: "#fff", padding: spacing.md, borderRadius: radius.md, fontSize: 16, marginBottom: spacing.sm },
  submit: { backgroundColor: colors.brandSecondary, padding: 16, borderRadius: radius.lg, alignItems: "center", marginTop: spacing.sm },
  submitText: { color: colors.onBrandSecondary, fontWeight: "800", fontSize: 16 },
  err: { color: "#FFA0A0", marginBottom: spacing.xs },
  disclaim: { color: colors.brandTertiary, fontSize: 13, marginTop: spacing.md, lineHeight: 19 },
  mvp: { color: "rgba(255,255,255,0.5)", fontSize: 11, marginTop: spacing.sm, fontStyle: "italic" },
});
