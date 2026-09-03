import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Svg, { Circle, G, Line, Polyline, Text as SvgText } from "react-native-svg";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { signIn, authedFetch, cachePatientOnboarding, getCachedPatientProfile, hasAcceptedConsent, type Me } from "@/src/auth";

const DEEP_GREEN = "#07563A";
const INK = "#063C2C";
const MUTED = "#45545E";
const WARM_WHITE = "#FCFAF7";

type Overlay = "auth" | "how" | "families" | null;
type AuthIntent = "start" | "signin";

const PREVIEW_SCORES = [64, 74, 80, 87, 78, 89, 98];

function RehynBrand({ compact = false }: { compact?: boolean }) {
  return (
    <View style={styles.brandRow}>
      <View style={[styles.brandMark, compact && styles.brandMarkCompact]}>
        <Ionicons name="pulse" size={compact ? 22 : 28} color="#FFFFFF" />
      </View>
      <Text style={[styles.brandName, compact && styles.brandNameCompact]}>Rehyn</Text>
    </View>
  );
}

function ProgressPreviewChart() {
  const coordinates = PREVIEW_SCORES.map((score, index) => ({
    x: 104 + index * 80,
    y: 174 - ((score - 60) / 40) * 138,
  }));
  const endpoint = coordinates[coordinates.length - 1];

  return (
    <Svg width="100%" height={230} viewBox="0 0 620 230" testID="signin-progress-preview">
      {[100, 80, 60].map((tick) => {
        const y = 174 - ((tick - 60) / 40) * 138;
        return (
          <G key={tick}>
            <Line x1={62} y1={y} x2={600} y2={y} stroke="#E5E4DF" strokeWidth={1.3} strokeDasharray={tick === 60 ? undefined : "6 6"} />
            <SvgText x={48} y={y + 6} fill="#273944" fontSize={17} textAnchor="end">{tick}</SvgText>
          </G>
        );
      })}
      <Polyline
        points={coordinates.map((point) => `${point.x},${point.y}`).join(" ")}
        fill="none"
        stroke="#4A8061"
        strokeWidth={3.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {coordinates.map((point, index) => (
        <Circle key={index} cx={point.x} cy={point.y} r={7} fill="#397653" stroke={WARM_WHITE} strokeWidth={1.5} />
      ))}
      <Circle cx={endpoint.x} cy={endpoint.y} r={24} fill="#5FA078" opacity={0.12} />
      <Circle cx={endpoint.x} cy={endpoint.y} r={16} fill="#5FA078" opacity={0.2} />
      <Circle cx={endpoint.x} cy={endpoint.y} r={10} fill={DEEP_GREEN} stroke="#FFFFFF" strokeWidth={3} />
      <Circle cx={endpoint.x} cy={endpoint.y} r={3} fill="#FFFFFF" />
      <SvgText x={63} y={215} fill="#273944" fontSize={17}>Jun 12</SvgText>
      <SvgText x={600} y={215} fill="#273944" fontSize={17} textAnchor="end">Aug 28</SvgText>
    </Svg>
  );
}

export default function SignInScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isWide = width >= 980;
  const isMediumDesktop = isWide && width < 1500;
  const showHeaderSignIn = width >= 520;
  const [overlay, setOverlay] = useState<Overlay>(null);
  const [authIntent, setAuthIntent] = useState<AuthIntent>("start");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [trialCode, setTrialCode] = useState("");
  const [showTrialCode, setShowTrialCode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const routePatientAfterLogin = async (user: Me) => {
    // The sign-in response carries the account state saved in MongoDB:
    // consent_accepted and onboarding_complete are true for a returning
    // account, so the Terms and the initial survey are shown only to a new
    // account (or one that never finished them).
    if (user.consent_accepted !== true) {
      if (!(await hasAcceptedConsent(user.id))) {
        router.replace("/consent");
        return;
      }
    }
    if (user.onboarding_complete === true) {
      router.replace("/");
      return;
    }
    const cachedProfile = await getCachedPatientProfile(user.id);
    try {
      const response = await authedFetch("/api/users/onboarding");
      const onboarding = response.ok ? await response.json() : null;
      if (onboarding?.onboarding_complete) {
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

  const openAuth = (intent: AuthIntent) => {
    setAuthIntent(intent);
    setErr(null);
    setOverlay("auth");
    Haptics.selectionAsync();
  };

  const closeOverlay = () => {
    if (loading) return;
    setOverlay(null);
    setErr(null);
  };

  const submit = async () => {
    if (!name.trim() || !email.trim() || !trialCode.trim()) {
      setErr("Enter your name, email, and trial code to continue.");
      return;
    }
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setErr("Enter a valid email address.");
      return;
    }

    setLoading(true);
    setErr(null);
    try {
      const user = await signIn(email.trim(), name.trim(), "patient", trialCode.trim());
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setOverlay(null);
      await routePatientAfterLogin(user);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Sign-in failed. Try again.";
      setErr(message);
    } finally {
      setLoading(false);
    }
  };

  const openPrivacy = () => {
    setOverlay(null);
    router.push("/privacy-policy" as never);
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <ScrollView contentContainerStyle={[styles.scrollContent, { paddingBottom: Math.max(insets.bottom, spacing.lg) }]} showsVerticalScrollIndicator={false}>
        <View style={[styles.page, !isWide && styles.pageCompact]}>
          <View style={styles.header}>
            <RehynBrand compact={!isWide} />
            <View style={[styles.headerActions, !isWide && styles.headerActionsCompact]}>
              {isWide ? (
                <>
                  <Pressable accessibilityRole="link" onPress={() => setOverlay("how")} style={({ pressed }) => [styles.navLink, pressed && styles.pressed]}>
                    <Text style={styles.navLinkText}>How it works</Text>
                  </Pressable>
                  <Pressable accessibilityRole="link" onPress={() => setOverlay("families")} style={({ pressed }) => [styles.navLink, pressed && styles.pressed]}>
                    <Text style={styles.navLinkText}>For families</Text>
                  </Pressable>
                </>
              ) : null}
              {showHeaderSignIn ? (
                <Pressable testID="signin-open-form" onPress={() => openAuth("signin")} style={({ pressed }) => [styles.navLink, pressed && styles.pressed]}>
                  <Text style={styles.navLinkText}>Sign in</Text>
                </Pressable>
              ) : null}
              <Pressable testID="signin-start-free" onPress={() => openAuth("start")} style={({ pressed }) => [styles.headerCta, !isWide && styles.headerCtaCompact, pressed && styles.buttonPressed]}>
                <Text style={styles.headerCtaText}>Start free</Text>
              </Pressable>
            </View>
          </View>

          <View style={[styles.hero, isMediumDesktop && styles.heroMedium, !isWide && styles.heroCompact]}>
            <View style={[styles.heroCopy, isMediumDesktop && styles.heroCopyMedium, !isWide && styles.heroCopyCompact]}>
              <Text style={styles.eyebrow}>STROKE RECOVERY AT HOME</Text>
              <Text style={[styles.heroTitle, isMediumDesktop && styles.heroTitleMedium, !isWide && styles.heroTitleCompact]}>One clear next step.</Text>
              <Text style={[styles.heroBody, !isWide && styles.heroBodyCompact]}>Understand your movement, follow a personal plan and see your progress.</Text>
              <Pressable testID="signin-start-assessment" onPress={() => openAuth("start")} style={({ pressed }) => [styles.primaryCta, !isWide && styles.primaryCtaCompact, pressed && styles.buttonPressed]}>
                <Text style={styles.primaryCtaText}>Start your assessment</Text>
              </Pressable>
              <Text style={styles.reassurance}>About 3 minutes  ·  Use alongside your clinical team</Text>
            </View>

            <View style={[styles.previewCard, !isWide && styles.previewCardCompact]}>
              <View style={styles.previewHeader}>
                <Text style={[styles.previewGreeting, !isWide && styles.previewGreetingCompact]}>Good morning, Molly</Text>
                <Ionicons name="notifications-outline" size={30} color="#397653" />
              </View>
              <Pressable accessibilityLabel="Start rehab preview" onPress={() => openAuth("start")} style={({ pressed }) => [styles.previewButton, pressed && styles.buttonPressed]}>
                <View style={styles.playDisc}><Ionicons name="play" size={18} color={DEEP_GREEN} /></View>
                <Text style={styles.previewButtonText}>Start rehab</Text>
              </Pressable>
              <View style={styles.previewDivider} />
              <Text style={styles.previewTitle}>Your progress</Text>
              <ProgressPreviewChart />
            </View>
          </View>
        </View>
      </ScrollView>

      <Modal visible={overlay !== null} transparent animationType="fade" onRequestClose={closeOverlay}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.modalRoot}>
          <Pressable accessibilityLabel="Close" onPress={closeOverlay} style={StyleSheet.absoluteFill} />
          <View style={[styles.modalCard, overlay !== "auth" && styles.infoCard]} accessibilityViewIsModal>
            <Pressable accessibilityLabel="Close" onPress={closeOverlay} style={({ pressed }) => [styles.closeButton, pressed && styles.pressed]}>
              <Ionicons name="close" size={24} color={INK} />
            </Pressable>

            {overlay === "auth" ? (
              <ScrollView contentContainerStyle={styles.formContent} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
                <View style={styles.modalBrand}><RehynBrand compact /></View>
                <Text style={styles.formTitle}>{authIntent === "start" ? "Start free" : "Sign in to Rehyn"}</Text>
                <Text style={styles.formSubtitle}>Enter your details and trial code to continue.</Text>

                <Text style={styles.inputLabel}>Your name</Text>
                <TextInput
                  value={name}
                  onChangeText={(value) => { setName(value); setErr(null); }}
                  placeholder="Name"
                  placeholderTextColor="#82908A"
                  style={styles.input}
                  testID="signin-name"
                  autoCapitalize="words"
                  autoComplete="name"
                  returnKeyType="next"
                />

                <Text style={styles.inputLabel}>Email</Text>
                <TextInput
                  value={email}
                  onChangeText={(value) => { setEmail(value); setErr(null); }}
                  placeholder="you@example.com"
                  placeholderTextColor="#82908A"
                  style={styles.input}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoComplete="email"
                  testID="signin-email"
                  returnKeyType="next"
                />

                <Text style={styles.inputLabel}>Trial code</Text>
                <View style={styles.trialInputShell}>
                  <TextInput
                    value={trialCode}
                    onChangeText={(value) => { setTrialCode(value); setErr(null); }}
                    placeholder="Enter your trial code"
                    placeholderTextColor="#82908A"
                    style={styles.trialInput}
                    autoCapitalize="none"
                    autoCorrect={false}
                    secureTextEntry={!showTrialCode}
                    textContentType="password"
                    testID="signin-trial-code"
                    returnKeyType="go"
                    onSubmitEditing={submit}
                  />
                  <Pressable accessibilityLabel={showTrialCode ? "Hide trial code" : "Show trial code"} onPress={() => setShowTrialCode((value) => !value)} style={({ pressed }) => [styles.eyeButton, pressed && styles.pressed]}>
                    <Ionicons name={showTrialCode ? "eye-off-outline" : "eye-outline"} size={22} color={MUTED} />
                  </Pressable>
                </View>
                <Text style={styles.trialHint}>Trial access is required to use Rehyn.</Text>

                {err ? <Text accessibilityRole="alert" testID="signin-error" style={styles.error}>{err}</Text> : null}
                <Pressable testID="signin-submit" disabled={loading} onPress={submit} style={({ pressed }) => [styles.submitButton, loading && styles.disabled, pressed && !loading && styles.buttonPressed]}>
                  {loading ? <ActivityIndicator color="#FFFFFF" /> : <><Text style={styles.submitText}>Continue to Rehyn</Text><Ionicons name="arrow-forward" size={21} color="#FFFFFF" /></>}
                </Pressable>
                <Pressable accessibilityRole="link" onPress={openPrivacy} hitSlop={8} style={({ pressed }) => [styles.privacyButton, pressed && styles.pressed]}>
                  <Text style={styles.privacyText}>Privacy policy</Text>
                </Pressable>
              </ScrollView>
            ) : (
              <View style={styles.infoContent}>
                <View style={styles.infoIcon}>
                  <Ionicons name={overlay === "how" ? "footsteps-outline" : "people-outline"} size={30} color={DEEP_GREEN} />
                </View>
                <Text style={styles.infoTitle}>{overlay === "how" ? "How Rehyn works" : "Support for families"}</Text>
                <Text style={styles.infoBody}>
                  {overlay === "how"
                    ? "Start with a short movement assessment. Rehyn turns what it observes into a personal plan, guided rehab and progress you can follow over time."
                    : "A family member or carer can help with setup, safe positioning and recording while the patient remains in control of their own profile and plan."}
                </Text>
                <Pressable onPress={() => openAuth("start")} style={({ pressed }) => [styles.submitButton, pressed && styles.buttonPressed]}>
                  <Text style={styles.submitText}>Start free</Text>
                  <Ionicons name="arrow-forward" size={21} color="#FFFFFF" />
                </Pressable>
              </View>
            )}
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: WARM_WHITE },
  scrollContent: { flexGrow: 1 },
  page: { width: "100%", maxWidth: 1600, alignSelf: "center", paddingHorizontal: 56, paddingTop: 30 },
  pageCompact: { paddingHorizontal: 20, paddingTop: 18 },
  header: { minHeight: 76, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.lg },
  brandRow: { flexDirection: "row", alignItems: "center", gap: 16 },
  brandMark: { width: 64, height: 64, borderRadius: 12, backgroundColor: DEEP_GREEN, alignItems: "center", justifyContent: "center", shadowColor: "#062C20", shadowOpacity: 0.16, shadowRadius: 10, shadowOffset: { width: 0, height: 4 } },
  brandMarkCompact: { width: 48, height: 48, borderRadius: 10 },
  brandName: { color: INK, fontSize: 46, lineHeight: 52, fontWeight: "800" },
  brandNameCompact: { fontSize: 30, lineHeight: 36 },
  headerActions: { flexDirection: "row", alignItems: "center", justifyContent: "flex-end", gap: 26 },
  headerActionsCompact: { gap: 8 },
  navLink: { minHeight: 48, paddingHorizontal: 10, alignItems: "center", justifyContent: "center" },
  navLinkText: { color: INK, fontSize: 19, fontWeight: "700" },
  headerCta: { minWidth: 176, minHeight: 64, paddingHorizontal: 26, borderRadius: 10, backgroundColor: DEEP_GREEN, alignItems: "center", justifyContent: "center" },
  headerCtaCompact: { minWidth: 112, minHeight: 50, paddingHorizontal: 16 },
  headerCtaText: { color: "#FFFFFF", fontSize: 21, fontWeight: "800" },
  hero: { flex: 1, minHeight: 610, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 58, paddingVertical: 32 },
  heroMedium: { gap: 40 },
  heroCompact: { minHeight: 0, flexDirection: "column", alignItems: "stretch", gap: 36, paddingVertical: 36 },
  heroCopy: { flex: 0.94, maxWidth: 730, paddingBottom: 22 },
  heroCopyMedium: { flex: 1.05 },
  heroCopyCompact: { maxWidth: 690, width: "100%", alignSelf: "center", paddingBottom: 0 },
  eyebrow: { color: DEEP_GREEN, fontSize: 22, lineHeight: 28, fontWeight: "800", marginBottom: 28 },
  heroTitle: { color: INK, fontSize: 66, lineHeight: 76, fontWeight: "800", marginBottom: 28 },
  heroTitleMedium: { fontSize: 52, lineHeight: 62 },
  heroTitleCompact: { fontSize: 45, lineHeight: 52, marginBottom: 20 },
  heroBody: { color: MUTED, fontSize: 28, lineHeight: 42, maxWidth: 660, marginBottom: 44 },
  heroBodyCompact: { fontSize: 21, lineHeight: 31, marginBottom: 30 },
  primaryCta: { width: 374, minHeight: 92, borderRadius: 10, backgroundColor: DEEP_GREEN, alignItems: "center", justifyContent: "center", paddingHorizontal: 26 },
  primaryCtaCompact: { width: "100%", maxWidth: 400, minHeight: 66 },
  primaryCtaText: { color: "#FFFFFF", fontSize: 25, fontWeight: "800", textAlign: "center" },
  reassurance: { color: "#344754", fontSize: 18, lineHeight: 26, marginTop: 32 },
  previewCard: { flex: 1, maxWidth: 760, minWidth: 0, minHeight: 550, borderRadius: radius.lg, borderWidth: 1, borderColor: "#DBDAD4", backgroundColor: "#FFFDFB", paddingHorizontal: 44, paddingTop: 38, paddingBottom: 22, shadowColor: "#5F6B63", shadowOpacity: 0.08, shadowRadius: 18, shadowOffset: { width: 0, height: 6 } },
  previewCardCompact: { width: "100%", maxWidth: 760, alignSelf: "center", minHeight: 0, paddingHorizontal: 22, paddingTop: 28 },
  previewHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md, marginBottom: 30 },
  previewGreeting: { flex: 1, color: INK, fontSize: 29, lineHeight: 36, fontWeight: "800" },
  previewGreetingCompact: { fontSize: 24, lineHeight: 30 },
  previewButton: { minHeight: 80, borderRadius: 11, backgroundColor: DEEP_GREEN, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 18, paddingHorizontal: 24 },
  playDisc: { width: 42, height: 42, borderRadius: 21, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center", paddingLeft: 2 },
  previewButtonText: { color: "#FFFFFF", fontSize: 24, fontWeight: "800" },
  previewDivider: { height: 1, backgroundColor: "#DAD9D4", marginVertical: 30 },
  previewTitle: { color: INK, fontSize: 24, lineHeight: 30, fontWeight: "800", marginBottom: 4 },
  modalRoot: { flex: 1, padding: 20, backgroundColor: "rgba(4,31,22,0.56)", alignItems: "center", justifyContent: "center" },
  modalCard: { width: "100%", maxWidth: 520, maxHeight: "92%", borderRadius: radius.lg, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#DADFD9", shadowColor: "#071E16", shadowOpacity: 0.22, shadowRadius: 30, shadowOffset: { width: 0, height: 14 } },
  infoCard: { maxWidth: 560 },
  closeButton: { position: "absolute", zIndex: 2, right: 18, top: 18, width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: "#F1F4F0" },
  modalBrand: { marginBottom: 26 },
  formContent: { paddingHorizontal: 34, paddingTop: 34, paddingBottom: 30 },
  formTitle: { color: INK, fontSize: 34, lineHeight: 41, fontWeight: "800", marginBottom: 8 },
  formSubtitle: { color: MUTED, fontSize: 17, lineHeight: 25, marginBottom: 26 },
  inputLabel: { color: INK, fontSize: 15, fontWeight: "800", marginBottom: 8 },
  input: { minHeight: 56, borderRadius: radius.sm, borderWidth: 1, borderColor: "#BFC9C2", backgroundColor: "#FFFFFF", color: INK, fontSize: 17, paddingHorizontal: 16, marginBottom: 18 },
  trialInputShell: { minHeight: 56, flexDirection: "row", alignItems: "center", borderRadius: radius.sm, borderWidth: 1, borderColor: "#BFC9C2", backgroundColor: "#FFFFFF", marginBottom: 8 },
  trialInput: { flex: 1, minWidth: 0, minHeight: 54, color: INK, fontSize: 17, paddingHorizontal: 16 },
  eyeButton: { width: 52, height: 54, alignItems: "center", justifyContent: "center" },
  trialHint: { color: MUTED, fontSize: 14, lineHeight: 20, marginBottom: 18 },
  error: { color: colors.error, fontSize: 15, lineHeight: 21, fontWeight: "700", backgroundColor: "#FFF2F1", borderRadius: radius.sm, padding: 12, marginBottom: 14 },
  submitButton: { minHeight: 60, borderRadius: 10, backgroundColor: DEEP_GREEN, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10, paddingHorizontal: 22 },
  submitText: { color: "#FFFFFF", fontSize: 18, fontWeight: "800" },
  privacyButton: { alignSelf: "center", padding: 10, marginTop: 12 },
  privacyText: { color: DEEP_GREEN, fontSize: 14, fontWeight: "700", textDecorationLine: "underline" },
  infoContent: { paddingHorizontal: 36, paddingTop: 58, paddingBottom: 34 },
  infoIcon: { width: 58, height: 58, borderRadius: 29, backgroundColor: "#E6F0E8", alignItems: "center", justifyContent: "center", marginBottom: 22 },
  infoTitle: { color: INK, fontSize: 30, lineHeight: 37, fontWeight: "800", marginBottom: 14 },
  infoBody: { color: MUTED, fontSize: 17, lineHeight: 28, marginBottom: 28 },
  pressed: { opacity: 0.68 },
  buttonPressed: { opacity: 0.84, transform: [{ scale: 0.99 }] },
  disabled: { opacity: 0.58 },
});
