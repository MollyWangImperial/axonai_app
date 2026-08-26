import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, KeyboardAvoidingView, Platform, Linking } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import * as WebBrowser from "expo-web-browser";
import { colors, spacing, radius } from "@/src/theme";
import { signIn, authedFetch, USER_KEY, USER_OBJ } from "@/src/auth";
import { storage } from "@/src/utils/storage";
import { API_BASE as BASE } from "@/src/config";

export default function SignInScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [role, setRole] = useState<"patient" | "therapist">("patient");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // On web — if we just returned from Emergent's Google auth flow, the URL hash
  // will contain `session_id=...`. We exchange it for our app user.
  useEffect(() => {
    if (Platform.OS !== "web") return;
    try {
      const hash = (window.location.hash || "").replace(/^#/, "");
      const qs = new URLSearchParams(hash);
      const sid = qs.get("session_id");
      if (sid) {
        // Clean URL so refresh doesn't re-run
        window.history.replaceState({}, document.title, window.location.pathname);
        handleGoogleSession(sid);
      }
    } catch {/* */}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleGoogleSession = async (sid: string) => {
    setGoogleLoading(true);
    setErr(null);
    try {
      const r = await fetch(`${BASE}/api/auth/google/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sid }),
      });
      if (!r.ok) throw new Error(await r.text());
      const u = await r.json();
      await storage.setItem(USER_KEY, u.id);
      await storage.setItem(USER_OBJ, JSON.stringify(u));
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      // Patient onboarding routing
      if (u.role === "therapist") {
        router.replace("/therapist");
      } else {
        try {
          const or = await authedFetch("/api/users/onboarding");
          const oj = await or.json();
          if (oj.onboarding_complete) {
            await storage.setItem("onboarding_complete_v1", "1");
            if (oj.profile?.preferred_name) await storage.setItem("preferred_name_v1", oj.profile.preferred_name);
            router.replace("/");
          } else router.replace("/onboarding");
        } catch { router.replace("/onboarding"); }
      }
    } catch (e) {
      setErr("Google sign-in failed. Please try again.");
    } finally {
      setGoogleLoading(false);
    }
  };

  const startGoogleAuth = async () => {
    Haptics.selectionAsync();
    setErr(null);
    // Build the redirect URL — Emergent appends the session_id as a URL hash.
    const redirect = Platform.OS === "web"
      ? `${window.location.origin}/sign-in`
      : `neuromotion://sign-in`;
    const url = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirect)}`;
    if (Platform.OS === "web") {
      window.location.href = url;
      return;
    }
    setGoogleLoading(true);
    try {
      const res = await WebBrowser.openAuthSessionAsync(url, redirect);
      if (res.type === "success" && res.url) {
        const m = res.url.match(/[#?]session_id=([^&]+)/);
        if (m && m[1]) {
          await handleGoogleSession(decodeURIComponent(m[1]));
          return;
        }
        setErr("Google sign-in incomplete. Please try again.");
      } else if (res.type === "cancel") {
        // user cancelled — no error toast
      } else {
        setErr("Google sign-in didn't complete.");
      }
    } catch (e) {
      setErr("Couldn't open Google sign-in.");
    } finally {
      setGoogleLoading(false);
    }
  };

  const submit = async () => {
    if (!email.trim() || !name.trim()) {
      setErr("Please enter your name and email.");
      return;
    }
    setLoading(true); setErr(null);
    try {
      const u = await signIn(email.trim(), name.trim(), role);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      if (u.role === "therapist") {
        router.replace("/therapist");
        return;
      }
      // Patient — check whether onboarding is complete
      try {
        const r = await authedFetch("/api/users/onboarding");
        const j = await r.json();
        if (j.onboarding_complete) {
          await storage.setItem("onboarding_complete_v1", "1");
          if (j.profile?.preferred_name) await storage.setItem("preferred_name_v1", j.profile.preferred_name);
          router.replace("/");
        } else {
          router.replace("/onboarding");
        }
      } catch {
        // Fail-safe: go to onboarding for any new account flow
        router.replace("/onboarding");
      }
    } catch (e) {
      setErr("Sign-in failed. Try again.");
    } finally { setLoading(false); }
  };

  return (
    <LinearGradient colors={[colors.brandPrimary, "#1C201D"]} style={[styles.container, { paddingTop: insets.top + spacing.lg }]}>
      <View style={styles.brand}>
        <Ionicons name="heart" size={32} color="#fff" />
        <Text style={styles.brandText}>Rehyn</Text>
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
        {role === "patient" && (
          <>
            <Pressable
              onPress={startGoogleAuth}
              disabled={googleLoading}
              style={[styles.googleBtn, googleLoading && { opacity: 0.6 }]}
              testID="signin-google"
            >
              {googleLoading ? <ActivityIndicator color={colors.brandPrimary} /> : (
                <>
                  <Ionicons name="logo-google" size={20} color={colors.brandPrimary} />
                  <Text style={styles.googleBtnText}>Continue with Google</Text>
                </>
              )}
            </Pressable>
            <View style={styles.divider}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>OR EMAIL</Text>
              <View style={styles.dividerLine} />
            </View>
          </>
        )}
        <TextInput value={name} onChangeText={setName} placeholder="Your name" placeholderTextColor="#bcc2ba" style={styles.input} testID="signin-name" autoCapitalize="words" />
        <TextInput value={email} onChangeText={setEmail} placeholder="Email" placeholderTextColor="#bcc2ba" style={styles.input} keyboardType="email-address" autoCapitalize="none" testID="signin-email" />
        {err && <Text style={styles.err}>{err}</Text>}
        <Pressable onPress={submit} style={styles.submit} disabled={loading} testID="signin-submit">
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.submitText}>{role === "patient" ? "Continue with Email" : "Open therapist portal"}</Text>}
        </Pressable>
        <Text style={styles.disclaim}>
          New here? Your patient account starts with <Text style={{ color: colors.brandSecondary, fontWeight: "800" }}>100 credits</Text> — enough for one assessment, one personalized plan, and one guided exercise.
        </Text>
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
  googleBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10, backgroundColor: "#fff", padding: 14, borderRadius: radius.lg, minHeight: 52, marginBottom: spacing.md },
  googleBtnText: { color: colors.brandPrimary, fontWeight: "800", fontSize: 15 },
  divider: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginVertical: spacing.sm },
  dividerLine: { flex: 1, height: 1, backgroundColor: "rgba(255,255,255,0.2)" },
  dividerText: { color: "rgba(255,255,255,0.55)", fontSize: 11, fontWeight: "700", letterSpacing: 1 },
  submit: { backgroundColor: colors.brandSecondary, padding: 16, borderRadius: radius.lg, alignItems: "center", marginTop: spacing.sm },
  submitText: { color: colors.onBrandSecondary, fontWeight: "800", fontSize: 16 },
  err: { color: "#FFA0A0", marginBottom: spacing.xs },
  disclaim: { color: colors.brandTertiary, fontSize: 13, marginTop: spacing.md, lineHeight: 19 },
  mvp: { color: "rgba(255,255,255,0.5)", fontSize: 11, marginTop: spacing.sm, fontStyle: "italic" },
});
