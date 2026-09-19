import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
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
import { Image as ExpoImage } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, radius } from "@/src/theme";
import LandingDiscoverySurvey from "@/src/components/LandingDiscoverySurvey";
import { signIn, completeSignInHandoff, authedFetch, cachePatientOnboarding, getCachedPatientProfile, hasAcceptedConsent, type Me } from "@/src/auth";

// Sampled from the supplied Rehyn logo; shared by every landing-page accent.
const DEEP_GREEN = "#004A38";
// Sampled from the brighter green headline in the supplied colour reference.
const LIGHT_GREEN = "#3DD45A";
const INK = "#083547";
const MUTED = "#254D63";
const WARM_WHITE = "#FCFAF7";

type Overlay = "auth" | "how" | "about" | "contact" | "discovery" | null;
type AuthIntent = "start" | "signin";

function RehynBrand({ compact = false }: { compact?: boolean }) {
  return (
    <View style={[styles.brandFrame, compact && styles.brandFrameCompact]}>
      <Image
        source={require("../assets/images/rehyn-logo-transparent.png")}
        accessibilityLabel="Rehyn"
        resizeMode="contain"
        style={[styles.brandLogo, compact && styles.brandLogoCompact]}
      />
    </View>
  );
}

export default function SignInScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { auth, handoff } = useLocalSearchParams<{ auth?: string | string[]; handoff?: string | string[] }>();
  const requestedAuth = Array.isArray(auth) ? auth[0] : auth;
  const requestedHandoff = Array.isArray(handoff) ? handoff[0] : handoff;
  const { width, height } = useWindowDimensions();
  const isWide = width >= 1120;
  const isSmall = width < 600;
  const isPhone = width < 700;
  const isSurveyCompact = width < 1100;
  const pageHeight = Math.max(height - insets.top - insets.bottom, isWide ? 620 : 0);
  const phoneHeaderHeight = 72;
  const phonePhotoHeight = Math.round(width * 0.875);
  const phoneHeroHeight = Math.max(700, pageHeight - phoneHeaderHeight);
  const phoneCopyHeight = Math.max(420, phoneHeroHeight - phonePhotoHeight);
  const headingSize = isWide ? Math.min(68, width * 0.038) : isSmall ? Math.min(40, width * 0.097) : 58;
  const [overlay, setOverlay] = useState<Overlay>(requestedAuth === "signin" || requestedAuth === "start" ? "auth" : null);
  const [authIntent, setAuthIntent] = useState<AuthIntent>(requestedAuth === "signin" ? "signin" : "start");
  const [discoveryFocus, setDiscoveryFocus] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [trialCode, setTrialCode] = useState("");
  const [showTrialCode, setShowTrialCode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [handoffError, setHandoffError] = useState<string | null>(null);
  const handoffStarted = useRef(false);

  const routePatientAfterLogin = useCallback(async (user: Me) => {
    // The sign-in response carries the account state saved in MongoDB:
    // consent_accepted and onboarding_complete are true for a returning
    // account, so the Terms and the initial survey are shown only to a new
    // account (or one that never finished them).
    const recoveryController = new AbortController();
    const recoveryTimeout = setTimeout(() => recoveryController.abort(), 10000);
    try {
      if (user.consent_accepted !== true) {
        if (!(await hasAcceptedConsent(user.id, recoveryController.signal))) {
          router.replace("/consent");
          return;
        }
      }
      if (user.onboarding_complete === true) {
        router.replace("/");
        return;
      }
      const cachedProfile = await getCachedPatientProfile(user.id);
      const response = await authedFetch("/api/users/onboarding", { signal: recoveryController.signal });
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
          signal: recoveryController.signal,
        });
        if (restore.ok) {
          const restored = await restore.json();
          await cachePatientOnboarding(user.id, restored.profile || cachedProfile);
          router.replace("/");
          return;
        }
      }
    } catch {
      const cachedProfile = await getCachedPatientProfile(user.id);
      if (cachedProfile) {
        router.replace("/");
        return;
      }
    } finally {
      clearTimeout(recoveryTimeout);
    }
    router.replace("/onboarding");
  }, [router]);

  useEffect(() => {
    if (!requestedHandoff || handoffStarted.current) return;
    handoffStarted.current = true;
    setHandoffError(null);
    void completeSignInHandoff(requestedHandoff)
      .then(routePatientAfterLogin)
      .catch((error) => {
        setHandoffError(error instanceof Error ? error.message : "We could not finish signing you in. Please try again.");
      });
  }, [requestedHandoff, routePatientAfterLogin]);

  const openAuth = (intent: AuthIntent, focus: string | null = null) => {
    setDiscoveryFocus(focus);
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
    if (!name.trim() || !email.trim()) {
      setErr("Enter your name and email to continue.");
      return;
    }
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setErr("Enter a valid email address.");
      return;
    }
    if (!trialCode.trim()) {
      setErr("Enter your trial code to continue.");
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

  if (requestedHandoff) {
    return (
      <View style={[styles.handoffScreen, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
        <RehynBrand />
        <View style={styles.handoffCard}>
          {handoffError ? (
            <>
              <Ionicons name="alert-circle-outline" size={42} color={colors.error} />
              <Text style={styles.handoffTitle}>Please sign in again</Text>
              <Text style={styles.handoffBody}>{handoffError}</Text>
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  if (Platform.OS === "web" && typeof window !== "undefined") window.location.assign("https://rehyn.com/?signin=1");
                  else router.replace("/sign-in");
                }}
                style={({ pressed }) => [styles.submitButton, pressed && styles.pressed]}
              >
                <Text style={styles.submitText}>Return to sign in</Text>
              </Pressable>
            </>
          ) : (
            <>
              <ActivityIndicator size="large" color={DEEP_GREEN} />
              <Text style={styles.handoffTitle}>Opening Rehyn…</Text>
              <Text style={styles.handoffBody}>Your secure sign-in is being completed.</Text>
            </>
          )}
        </View>
      </View>
    );
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <ScrollView
        contentContainerStyle={[styles.scrollContent, { paddingBottom: insets.bottom }]}
        showsVerticalScrollIndicator={false}
      >
        <View style={[styles.landing, { minHeight: pageHeight }]}>
          <View style={[styles.header, !isWide && styles.headerCompact, isPhone && styles.headerPhone]}>
            <RehynBrand compact={!isWide} />
            <View style={[styles.headerActions, !isWide && styles.headerActionsCompact]}>
              {isWide ? (
                <>
                  <Pressable accessibilityRole="button" onPress={() => setOverlay("how")} style={({ pressed }) => [styles.navLink, pressed && styles.pressed]}>
                    <Text style={styles.navLinkText}>How it works</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" onPress={() => openAuth("signin")} style={({ pressed }) => [styles.navLink, pressed && styles.pressed]}>
                    <Text style={styles.navLinkText}>Your programme</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" onPress={() => setOverlay("about")} style={({ pressed }) => [styles.navLink, pressed && styles.pressed]}>
                    <Text style={styles.navLinkText}>About</Text>
                  </Pressable>
                  <View style={styles.navDivider} />
                  <Pressable accessibilityRole="button" onPress={() => setOverlay("contact")} style={({ pressed }) => [styles.navLink, pressed && styles.pressed]}>
                    <Text style={styles.navLinkText}>Talk to us</Text>
                  </Pressable>
                </>
              ) : null}
              <Pressable
                testID="signin-header"
                accessibilityRole="button"
                onPress={() => openAuth("signin")}
                style={({ pressed }) => [styles.signInButton, !isWide && styles.signInButtonCompact, isPhone && styles.signInButtonPhone, pressed && styles.buttonPressed]}
              >
                <Text style={[styles.signInButtonText, !isWide && styles.signInButtonTextCompact]}>Sign in</Text>
              </Pressable>
            </View>
          </View>
          {!isWide && !isPhone ? (
            <View style={styles.mobileNavigation}>
              <Pressable accessibilityRole="button" onPress={() => setOverlay("how")} style={({ pressed }) => [styles.navLink, pressed && styles.pressed]}>
                <Text style={styles.mobileNavText}>How it works</Text>
              </Pressable>
              <Pressable accessibilityRole="button" onPress={() => setOverlay("about")} style={({ pressed }) => [styles.navLink, pressed && styles.pressed]}>
                <Text style={styles.mobileNavText}>About</Text>
              </Pressable>
            </View>
          ) : null}
          <View style={[styles.hero, isWide ? { minHeight: Math.max(620, pageHeight - 92) } : isPhone ? [styles.heroPhone, { minHeight: phoneHeroHeight }] : styles.heroCompact]}>
            <ExpoImage
              source={require("../assets/images/rehyn-landing-hero-background.png")}
              contentFit="cover"
              contentPosition={isWide ? "center" : isPhone ? { left: "90%", top: "50%" } : { left: "70%", top: "50%" }}
              accessibilityLabel="A man practising a seated reaching movement at home with a phone on a tripod."
              style={[
                isPhone ? [styles.heroImagePhone, { height: phonePhotoHeight }] : styles.heroImage,
                isWide && Platform.OS === "web"
                  ? ({ top: -100, bottom: "auto", height: "calc(100% + 100px)" } as never)
                  : null,
                !isWide && !isPhone && styles.heroImageCompact,
              ]}
            />
            {!isPhone ? (
              <View
                style={[
                  styles.heroPanel,
                  isWide
                    ? Platform.OS === "web"
                      ? ({ width: "100%", clipPath: "polygon(0 0, 44.2% 0, 43.6% 6%, 42.9% 12%, 42.2% 19%, 41.5% 27%, 40.8% 35%, 40.5% 43%, 40.7% 51%, 41.3% 59%, 42.2% 67%, 43.5% 75%, 45.0% 83%, 47.0% 91%, 50.0% 100%, 0 100%)" } as never)
                      : styles.heroPanelDesktopNative
                    : styles.heroPanelCompact,
                ]}
              />
            ) : null}
            <View style={[styles.heroContent, !isWide && styles.heroContentCompact, isPhone && [styles.heroContentPhone, { minHeight: phoneCopyHeight }]]}>
              <View
                accessible
                accessibilityRole="header"
                accessibilityLabel="More progress. More confidence. All from home."
                style={styles.heroHeadingBlock}
              >
                <Text testID="signin-headline-progress" style={[styles.heroTitle, { fontSize: headingSize, lineHeight: headingSize * 1.08 }]}>More progress.</Text>
                <Text testID="signin-headline-confidence" style={[styles.heroTitle, { fontSize: headingSize, lineHeight: headingSize * 1.08 }]}>More confidence.</Text>
                <Text
                  testID="signin-static-phrase"
                  accessibilityElementsHidden
                  importantForAccessibility="no-hide-descendants"
                  style={[
                    styles.heroTitle,
                    styles.heroAccent,
                    { fontSize: headingSize, lineHeight: headingSize * 1.08 },
                  ]}
                >
                  All from home.
                </Text>
              </View>
              <Text
                testID="signin-hero-subtitle"
                style={[
                  styles.heroSubtitle,
                  isWide && width < 1350 && styles.heroSubtitleNarrowDesktop,
                  !isWide && styles.heroSubtitleCompact,
                  isPhone && styles.heroSubtitlePhone,
                ]}
              >
                {isPhone
                  ? "Personalised stroke rehabilitation,\nguided by experts and built around\neveryday life."
                  : isWide && width < 1350
                  ? "Personalised stroke rehabilitation,\nguided by experts and built around\neveryday life."
                  : "Personalised stroke rehabilitation, guided by\nexperts and built around everyday life."}
              </Text>
              <Pressable
                testID="signin-start-free"
                accessibilityRole="button"
                onPress={() => setOverlay("discovery")}
                style={({ pressed }) => [styles.heroCta, !isWide && styles.heroCtaCompact, isPhone && styles.heroCtaPhone, pressed && styles.buttonPressed]}
              >
                <Text style={[styles.heroCtaText, !isWide && styles.heroCtaTextCompact]}>See if Rehyn could help you</Text>
                <Ionicons name="arrow-forward" size={isWide ? 29 : 23} color={DEEP_GREEN} />
              </Pressable>
            </View>
          </View>
        </View>
      </ScrollView>

      <Modal visible={overlay !== null} transparent animationType="fade" onRequestClose={closeOverlay}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[styles.modalRoot, overlay === "discovery" && styles.discoveryModalRoot]}>
          <Pressable accessibilityLabel="Close" onPress={closeOverlay} style={StyleSheet.absoluteFill} />
          <View style={[styles.modalCard, overlay !== "auth" && styles.infoCard, overlay === "discovery" && styles.discoveryCard]} accessibilityViewIsModal>
            <Pressable accessibilityLabel="Close" onPress={closeOverlay} style={({ pressed }) => [styles.closeButton, overlay === "discovery" && (isSurveyCompact ? styles.discoveryCloseButtonCompact : styles.discoveryCloseButton), pressed && styles.pressed]}>
              <Ionicons name="close" size={overlay === "discovery" ? isSurveyCompact ? 28 : 38 : 24} color={INK} />
            </Pressable>

            {overlay === "discovery" ? (
              <LandingDiscoverySurvey onSignUp={(focus) => openAuth("start", focus)} />
            ) : overlay === "auth" ? (
              <ScrollView contentContainerStyle={styles.formContent} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
                <View style={styles.modalBrand}><RehynBrand compact /></View>
                <Text style={styles.formTitle}>{authIntent === "start" ? "Sign up to Rehyn" : "Sign in to Rehyn"}</Text>
                {discoveryFocus ? <Text testID="signin-discovery-focus" style={styles.focusNote}>Your focus: {discoveryFocus}</Text> : null}
                <Text style={styles.formSubtitle}>Enter your name and email to continue.</Text>

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
                <Text style={styles.infoTitle}>{overlay === "how" ? "How Rehyn works" : overlay === "contact" ? "Talk to us" : "About Rehyn"}</Text>
                <Text style={styles.infoBody}>
                  {overlay === "how"
                    ? "Start with a short movement assessment. Rehyn turns what it observes into a personal plan, guided rehab and progress you can follow over time."
                    : overlay === "contact"
                      ? "Have a question about getting started? Complete the short Rehyn check and we will guide you to the right next step."
                    : "Rehyn supports stroke rehabilitation at home with a short movement check, a programme shaped around you, and step-by-step exercise guidance. Family members and carers can help with setup while you stay in control of your profile and plan."}
                </Text>
                <Pressable onPress={() => overlay === "contact" ? setOverlay("discovery") : openAuth("start")} style={({ pressed }) => [styles.submitButton, pressed && styles.buttonPressed]}>
                  <Text style={styles.submitText}>{overlay === "contact" ? "See if Rehyn could help you" : "Start free"}</Text>
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
  handoffScreen: { flex: 1, minHeight: 520, backgroundColor: WARM_WHITE, alignItems: "center", justifyContent: "center", gap: 30, paddingHorizontal: 24 },
  handoffCard: { width: "100%", maxWidth: 520, minHeight: 250, borderRadius: radius.lg, borderWidth: 1, borderColor: "#DADFD9", backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center", padding: 38, shadowColor: "#071E16", shadowOpacity: 0.12, shadowRadius: 24, shadowOffset: { width: 0, height: 10 } },
  handoffTitle: { color: INK, fontSize: 30, lineHeight: 38, fontWeight: "800", textAlign: "center", marginTop: 22 },
  handoffBody: { color: MUTED, fontSize: 17, lineHeight: 26, textAlign: "center", marginTop: 8, marginBottom: 24 },
  scrollContent: { flexGrow: 1 },
  landing: { flex: 1, backgroundColor: "#FFFFFF", overflow: "hidden" },
  hero: { position: "relative", overflow: "hidden", flex: 1, backgroundColor: "#EDE9E2" },
  heroPhone: { flex: 0, backgroundColor: DEEP_GREEN },
  heroCompact: { minHeight: 715 },
  heroImage: { ...StyleSheet.absoluteFillObject, width: "100%", height: "100%" },
  heroImagePhone: { position: "relative", width: "100%", flexShrink: 0 },
  heroImageCompact: { top: 430, height: 285 },
  heroPanel: { ...StyleSheet.absoluteFillObject, backgroundColor: DEEP_GREEN },
  heroPanelDesktopNative: { right: undefined, width: "50.5%", borderTopRightRadius: 360, borderBottomRightRadius: 130 },
  heroPanelCompact: { width: "100%", bottom: undefined, height: 455, borderTopRightRadius: 0, borderBottomRightRadius: 90 },
  header: { minHeight: 92, paddingLeft: "6%", paddingRight: "4.35%", flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 20, zIndex: 1 },
  headerCompact: { minHeight: 80, paddingHorizontal: 16, gap: 8 },
  headerPhone: { minHeight: 72, paddingHorizontal: 18, backgroundColor: "#FFFFFF" },
  brandFrame: { width: 230, height: 83, overflow: "hidden" },
  brandFrameCompact: { width: 134, height: 54 },
  brandLogo: { width: 250, height: 83, marginLeft: -28 },
  brandLogoCompact: { width: 147, height: 49, marginLeft: -16 },
  headerActionsCompact: { flex: 1, minWidth: 0, justifyContent: "flex-end" },
  headerActions: { flexDirection: "row", alignItems: "center", gap: 28 },
  navLink: { minHeight: 48, paddingHorizontal: 6, alignItems: "center", justifyContent: "center" },
  navLinkText: { color: INK, fontSize: 20, fontWeight: "400" },
  navDivider: { width: 1, height: 44, backgroundColor: "#C8CBC8", marginHorizontal: 2 },
  signInButton: { minWidth: 150, minHeight: 60, paddingHorizontal: 28, borderRadius: 14, backgroundColor: LIGHT_GREEN, alignItems: "center", justifyContent: "center" },
  signInButtonCompact: { minWidth: 88, minHeight: 48, paddingHorizontal: 16, borderRadius: 10 },
  signInButtonPhone: { minWidth: 88, minHeight: 44, borderWidth: 1.5, borderColor: DEEP_GREEN, borderRadius: 24, backgroundColor: "#FFFFFF" },
  signInButtonText: { color: DEEP_GREEN, fontSize: 21, fontWeight: "800" },
  signInButtonTextCompact: { fontSize: 16 },
  mobileNavigation: { flexDirection: "row", gap: 24, paddingHorizontal: 22 },
  mobileNavText: { color: INK, fontSize: 16 },
  heroContent: { width: "43.5%", paddingLeft: "5.8%", paddingTop: 70, paddingBottom: 72, justifyContent: "center", alignItems: "flex-start", zIndex: 1 },
  heroContentCompact: { width: "100%", height: 455, paddingTop: 36, paddingHorizontal: 24, paddingBottom: 34, justifyContent: "flex-start" },
  heroContentPhone: { height: "auto", flexGrow: 1, paddingTop: 42, paddingHorizontal: 24, paddingBottom: 24, backgroundColor: DEEP_GREEN },
  heroHeadingBlock: { width: "100%", alignItems: "flex-start" },
  heroTitle: { color: "#FFFFFF", fontFamily: Platform.OS === "web" ? "Arial" : undefined, fontWeight: "800", letterSpacing: -2.6 },
  heroAccent: { color: LIGHT_GREEN },
  heroSubtitle: { color: "#FFFFFF", fontSize: 25, lineHeight: 34, fontWeight: "400", marginTop: 24, marginBottom: 54 },
  heroSubtitleNarrowDesktop: { maxWidth: 380 },
  heroSubtitleCompact: { fontSize: 16, lineHeight: 23, marginTop: 16, marginBottom: 24 },
  heroSubtitlePhone: { marginTop: 22, marginBottom: 34 },
  heroCta: { minWidth: 416, minHeight: 72, paddingHorizontal: 30, borderRadius: 13, backgroundColor: LIGHT_GREEN, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 20 },
  heroCtaCompact: { minWidth: 0, width: "100%", maxWidth: 360, minHeight: 56, paddingHorizontal: 20, borderRadius: 10 },
  heroCtaPhone: { maxWidth: "100%", minHeight: 58, borderRadius: 12 },
  heroCtaText: { color: DEEP_GREEN, fontSize: 22, fontWeight: "800" },
  heroCtaTextCompact: { fontSize: 16 },
  modalRoot: { flex: 1, padding: 20, backgroundColor: "rgba(4,31,22,0.56)", alignItems: "center", justifyContent: "center" },
  discoveryModalRoot: { padding: 0, backgroundColor: "#FFFFFF" },
  modalCard: { width: "100%", maxWidth: 520, maxHeight: "92%", borderRadius: radius.lg, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#DADFD9", shadowColor: "#071E16", shadowOpacity: 0.22, shadowRadius: 30, shadowOffset: { width: 0, height: 14 } },
  infoCard: { maxWidth: 560 },
  discoveryCard: { maxWidth: 1400, height: "100%", maxHeight: "100%", borderRadius: 0, borderWidth: 0, shadowOpacity: 0 },
  focusNote: { color: DEEP_GREEN, fontSize: 15, lineHeight: 22, fontWeight: "600", marginBottom: 12 },
  closeButton: { position: "absolute", zIndex: 2, right: 18, top: 18, width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: "#F1F4F0" },
  discoveryCloseButton: { right: 46, top: 42, width: 84, height: 84, borderRadius: 42 },
  discoveryCloseButtonCompact: { right: 18, top: 16, width: 54, height: 54, borderRadius: 27 },
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
