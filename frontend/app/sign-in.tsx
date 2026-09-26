import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import * as WebBrowser from "expo-web-browser";
import { colors, spacing, radius } from "@/src/theme";
import { signIn, authedFetch, cachePatientOnboarding, getCachedPatientProfile, USER_KEY, USER_OBJ } from "@/src/auth";
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

  const routePatientAfterLogin = async (user: { id: string }) => {
    const cachedProfile = await getCachedPatientProfile(user.id);
    try {
      const response = await authedFetch("/api/users/onboarding");
      const onboarding = await response.json();
      if (onboarding.onboarding_complete) {
        await cachePatientOnboarding(user.id, onboarding.profile);
        router.replace("/");
        return;
      }
      if (cachedProfile) {
        const restore = await authedFetch("/api/users/onboarding", {
          method: "POST",
          body: JSON.stringify(cachedProfile),
        });
        if (restore.ok) {
          const restored = await restore.json();
          await cachePatientOnboarding(user.id, restored.profile || cachedProfile);
          router.replace("/");
          return;
        }
      }
    } catch {
      if (cachedProfile) {
        router.replace("/");
        return;
      }
    }
    router.replace("/onboarding");
  };

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
        await routePatientAfterLogin(u);
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
      await routePatientAfterLogin(u);
    } catch (e) {
      setErr("Sign-in failed. Try again.");
    } finally { setLoading(false); }
  };

  return (
    <LinearGradient colors={["#355945", "#1E382D"]} style={[styles.container, { paddingTop: insets.top + spacing.lg }]}>
      <View style={styles.brand}>
        <Ionicons name="heart" size={32} color="#FFFDF5" />
        <Text style={styles.brandText}>Rehyn</Text>
      </View>
      <Text style={styles.title}>Welcome.</Text>
      <Text style={styles.sub}>Sign in to begin — or continue your recovery.</Text>

      <View style={styles.tabs}>
        <Pressable onPress={() => setRole("patient")} style={[styles.tab, role === "patient" && styles.tabActive]} testID="role-patient">
          <Ionicons name="person" size={18} color={role === "patient" ? "#244436" : "#FFFDF5"} />
          <Text style={[styles.tabText, role === "patient" && { color: "#244436" }]}>{"I'm a patient"}</Text>
        </Pressable>
        <Pressable onPress={() => setRole("therapist")} style={[styles.tab, role === "therapist" && styles.tabActive]} testID="role-therapist">
          <Ionicons name="medkit" size={18} color={role === "therapist" ? "#244436" : "#FFFDF5"} />
          <Text style={[styles.tabText, role === "therapist" && { color: "#244436" }]}>{"I'm a therapist"}</Text>
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
              {googleLoading ? <ActivityIndicator color="#244436" /> : (
                <>
                  <Ionicons name="logo-google" size={20} color="#244436" />
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
        <TextInput value={name} onChangeText={setName} placeholder="Your name" placeholderTextColor="#BFCBBE" style={styles.input} testID="signin-name" autoCapitalize="words" />
        <TextInput value={email} onChangeText={setEmail} placeholder="Email" placeholderTextColor="#BFCBBE" style={styles.input} keyboardType="email-address" autoCapitalize="none" testID="signin-email" />
        {err && <Text style={styles.err}>{err}</Text>}
        <Pressable onPress={submit} style={styles.submit} disabled={loading} testID="signin-submit">
          {loading ? <ActivityIndicator color="#FFFDF5" /> : <Text style={styles.submitText}>{role === "patient" ? "Continue with Email" : "Open therapist portal"}</Text>}
        </Pressable>
        <Text style={styles.disclaim}>
          New here? Your patient account starts with <Text style={{ color: "#F2D69D", fontWeight: "800" }}>100 credits</Text> — enough for one assessment, one personalized plan, and one guided exercise.
        </Text>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: spacing.lg },
  brand: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: spacing.xl },
  brandText: { color: "#FFFDF5", fontWeight: "800", fontSize: 24, letterSpacing: 0.8 },
  title: { color: "#FFFDF5", fontSize: 34, fontWeight: "800", marginBottom: 6, letterSpacing: -0.4 },
  sub: { color: "#DCE8D9", fontSize: 17, lineHeight: 24, marginBottom: spacing.xl },
  tabs: { flexDirection: "row", gap: 6, backgroundColor: "rgba(228, 238, 224, 0.18)", padding: 5, borderRadius: radius.lg, marginBottom: spacing.lg, borderWidth: 1, borderColor: "rgba(255, 253, 245, 0.18)" },
  tab: { flex: 1, flexDirection: "row", gap: 7, minHeight: 48, paddingHorizontal: 10, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  tabActive: { backgroundColor: "#FFFDF5", shadowColor: "#10271D", shadowOpacity: 0.18, shadowRadius: 5, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  tabText: { color: "#FFFDF5", fontWeight: "700", fontSize: 15 },
  input: { backgroundColor: "rgba(255, 253, 245, 0.13)", borderWidth: 1, borderColor: "rgba(235, 244, 230, 0.3)", color: "#FFFDF5", minHeight: 54, paddingHorizontal: spacing.md, paddingVertical: 12, borderRadius: radius.md, fontSize: 17, marginBottom: spacing.sm },
  googleBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10, backgroundColor: "#FFFDF5", paddingHorizontal: 16, paddingVertical: 12, borderRadius: radius.lg, minHeight: 54, marginBottom: spacing.md, shadowColor: "#10271D", shadowOpacity: 0.16, shadowRadius: 7, shadowOffset: { width: 0, height: 3 }, elevation: 2 },
  googleBtnText: { color: "#244436", fontWeight: "800", fontSize: 17 },
  divider: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginVertical: spacing.sm },
  dividerLine: { flex: 1, height: 1, backgroundColor: "rgba(235, 244, 230, 0.3)" },
  dividerText: { color: "#C8D7C5", fontSize: 12, fontWeight: "800", letterSpacing: 1.1 },
  submit: { backgroundColor: "#AFC7A8", minHeight: 54, paddingHorizontal: 16, paddingVertical: 12, borderRadius: radius.lg, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  submitText: { color: "#173126", fontWeight: "800", fontSize: 17 },
  err: { color: "#FFD2CC", fontSize: 16, lineHeight: 22, marginBottom: spacing.sm },
  disclaim: { color: "#DCE8D9", fontSize: 16, marginTop: spacing.lg, lineHeight: 23 },
  mvp: { color: "#C8D7C5", fontSize: 14, marginTop: spacing.sm, fontStyle: "italic" },
});
