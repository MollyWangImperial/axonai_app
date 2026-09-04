import { useCallback, useEffect, useRef, useState } from "react";
import {
  AccessibilityInfo,
  ActivityIndicator,
  Animated,
  Easing,
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
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { signIn, completeSignInHandoff, authedFetch, cachePatientOnboarding, getCachedPatientProfile, hasAcceptedConsent, type Me } from "@/src/auth";

const DEEP_GREEN = "#07563A";
const HERO_GREEN = "#3DD45A";
const INK = "#063C2C";
const MUTED = "#45545E";
const WARM_WHITE = "#FCFAF7";
const HERO_PHRASES = ["feels clearer.", "moves with you.", "shows small wins.", "gives you direction."];

type Overlay = "auth" | "how" | "families" | null;
type AuthIntent = "start" | "signin";

const PREVIEW_SCORES = [64, 72, 80, 86, 78, 88, 98];

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
    x: 56 + index * 36,
    y: 92 - ((score - 60) / 40) * 64,
  }));
  const endpoint = coordinates[coordinates.length - 1];

  return (
    <Svg width="100%" height={126} viewBox="0 0 300 126" testID="signin-progress-preview">
      {[100, 60].map((tick) => {
        const y = 92 - ((tick - 60) / 40) * 64;
        return (
          <G key={tick}>
            <Line x1={34} y1={y} x2={286} y2={y} stroke="#D9DED8" strokeWidth={1} strokeDasharray={tick === 100 ? "4 5" : undefined} />
            <SvgText x={27} y={y + 4} fill="#50605A" fontSize={10} textAnchor="end">{tick}</SvgText>
          </G>
        );
      })}
      <Polyline
        points={coordinates.map((point) => [point.x, point.y].join(",")).join(" ")}
        fill="none"
        stroke="#5A946B"
        strokeWidth={3}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {coordinates.map((point, index) => (
        <Circle key={index} cx={point.x} cy={point.y} r={4.5} fill="#397653" stroke="#FFFFFF" strokeWidth={1.2} />
      ))}
      <Circle cx={endpoint.x} cy={endpoint.y} r={15} fill="#5FA078" opacity={0.14} />
      <Circle cx={endpoint.x} cy={endpoint.y} r={9} fill={DEEP_GREEN} stroke="#FFFFFF" strokeWidth={2} />
      <Circle cx={endpoint.x} cy={endpoint.y} r={2.5} fill="#FFFFFF" />
      <SvgText x={35} y={119} fill="#50605A" fontSize={10}>Jun 12</SvgText>
      <SvgText x={286} y={119} fill="#50605A" fontSize={10} textAnchor="end">Aug 28</SvgText>
    </Svg>
  );
}

function QuickCheckPreview({ onPress }: { onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel="Preview the movement check" onPress={onPress} style={({ pressed }) => [styles.productCard, pressed && styles.productCardPressed]}>
      <View style={styles.previewTopline}>
        <Text style={styles.productEyebrow}>Quick check</Text>
        <Text style={styles.productMeta}>5 of 19</Text>
      </View>
      <View style={styles.miniProgressTrack}><View style={styles.miniProgressFill} /></View>
      <Text style={styles.productQuestion}>Which areas of your body were affected?</Text>
      <Text style={styles.productSupporting}>Select every area that applies.</Text>
      <View style={styles.choiceRow}>
        <View style={[styles.choiceTile, styles.choiceTileSelected]}>
          <Ionicons name="body-outline" size={24} color={DEEP_GREEN} />
          <Text style={styles.choiceText}>Upper limb</Text>
          <Ionicons name="checkmark-circle" size={19} color={DEEP_GREEN} />
        </View>
        <View style={styles.choiceTile}>
          <Ionicons name="walk-outline" size={24} color={DEEP_GREEN} />
          <Text style={styles.choiceText}>Lower limb</Text>
        </View>
      </View>
    </Pressable>
  );
}

function PlanPreview({ onPress }: { onPress: () => void }) {
  return (
    <View style={styles.productCard}>
      <View style={styles.previewTopline}>
        <Text style={styles.productEyebrow}>Today&apos;s plan</Text>
        <Text style={styles.productMeta}>3 activities</Text>
      </View>
      <View style={styles.planContent}>
        <View style={styles.exerciseIllustration}>
          <Ionicons name="accessibility-outline" size={54} color={DEEP_GREEN} />
        </View>
        <View style={styles.exerciseCopy}>
          <Text style={styles.exerciseTitle}>Seated arm lift</Text>
          <Text style={styles.productSupporting}>10 reps  ·  2 sets</Text>
        </View>
      </View>
      <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [styles.productButton, pressed && styles.buttonPressed]}>
        <Ionicons name="play" size={16} color="#FFFFFF" />
        <Text style={styles.productButtonText}>Start activity</Text>
      </Pressable>
    </View>
  );
}

function ProgressPreview({ onPress }: { onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel="Preview your progress" onPress={onPress} style={({ pressed }) => [styles.productCard, pressed && styles.productCardPressed]}>
      <View style={styles.previewTopline}>
        <Text style={styles.productEyebrow}>Your progress</Text>
        <View style={styles.previewFilter}>
          <Text style={styles.previewFilterText}>Reaching</Text>
          <Ionicons name="chevron-down" size={13} color={DEEP_GREEN} />
        </View>
      </View>
      <Text style={styles.progressMessage}>Your reaching is improving</Text>
      <ProgressPreviewChart />
    </Pressable>
  );
}

export default function SignInScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { auth, handoff } = useLocalSearchParams<{ auth?: string | string[]; handoff?: string | string[] }>();
  const requestedAuth = Array.isArray(auth) ? auth[0] : auth;
  const requestedHandoff = Array.isArray(handoff) ? handoff[0] : handoff;
  const { width } = useWindowDimensions();
  const isWide = width >= 980;
  const showHeaderSignIn = width >= 520;
  const [overlay, setOverlay] = useState<Overlay>(requestedAuth === "signin" || requestedAuth === "start" ? "auth" : null);
  const [authIntent, setAuthIntent] = useState<AuthIntent>(requestedAuth === "signin" ? "signin" : "start");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [trialCode, setTrialCode] = useState("");
  const [showTrialCode, setShowTrialCode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [reduceMotion, setReduceMotion] = useState(false);
  const [phraseIndex, setPhraseIndex] = useState(0);
  const phraseOpacity = useRef(new Animated.Value(1)).current;
  const phraseOffset = useRef(new Animated.Value(0)).current;
  const backgroundDrift = useRef(new Animated.Value(0)).current;
  const backgroundTwist = useRef(new Animated.Value(0)).current;
  const stageEntries = useRef([new Animated.Value(0), new Animated.Value(0), new Animated.Value(0)]).current;

  useEffect(() => {
    let mounted = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((enabled) => {
      if (mounted) setReduceMotion(enabled);
    });
    const subscription = AccessibilityInfo.addEventListener("reduceMotionChanged", setReduceMotion);
    return () => {
      mounted = false;
      subscription.remove();
    };
  }, []);

  useEffect(() => {
    if (reduceMotion) {
      backgroundDrift.setValue(0.4);
      backgroundTwist.setValue(0.5);
      stageEntries.forEach((entry) => entry.setValue(1));
      return;
    }

    stageEntries.forEach((entry) => entry.setValue(0));
    Animated.stagger(
      140,
      stageEntries.map((entry) => Animated.timing(entry, {
        toValue: 1,
        duration: 650,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      })),
    ).start();

    const drift = Animated.loop(
      Animated.sequence([
        Animated.timing(backgroundDrift, { toValue: 1, duration: 3800, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        Animated.timing(backgroundDrift, { toValue: 0, duration: 3800, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
      ]),
    );
    const twist = Animated.loop(
      Animated.sequence([
        Animated.timing(backgroundTwist, { toValue: 1, duration: 5000, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        Animated.timing(backgroundTwist, { toValue: 0, duration: 5000, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
      ]),
    );
    Animated.parallel([drift, twist]).start();
    return () => {
      drift.stop();
      twist.stop();
    };
  }, [backgroundDrift, backgroundTwist, reduceMotion, stageEntries]);

  useEffect(() => {
    if (reduceMotion) {
      setPhraseIndex(0);
      phraseOpacity.setValue(1);
      phraseOffset.setValue(0);
      return;
    }
    const timer = setInterval(() => {
      Animated.parallel([
        Animated.timing(phraseOpacity, { toValue: 0, duration: 170, useNativeDriver: true }),
        Animated.timing(phraseOffset, { toValue: -10, duration: 170, easing: Easing.in(Easing.quad), useNativeDriver: true }),
      ]).start(() => {
        setPhraseIndex((current) => (current + 1) % HERO_PHRASES.length);
        phraseOffset.setValue(12);
        Animated.parallel([
          Animated.timing(phraseOpacity, { toValue: 1, duration: 280, useNativeDriver: true }),
          Animated.timing(phraseOffset, { toValue: 0, duration: 280, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
        ]).start();
      });
    }, 2600);
    return () => clearInterval(timer);
  }, [phraseOffset, phraseOpacity, reduceMotion]);
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
    if (!name.trim() || !email.trim()) {
      setErr("Enter your name and email to continue.");
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

  const backgroundTranslateX = backgroundDrift.interpolate({ inputRange: [0, 1], outputRange: [-28, 30] });
  const backgroundTranslateY = backgroundDrift.interpolate({ inputRange: [0, 1], outputRange: [-12, 15] });
  const backgroundScale = backgroundDrift.interpolate({ inputRange: [0, 1], outputRange: [1.02, 1.09] });
  const backgroundRotate = backgroundDrift.interpolate({ inputRange: [0, 1], outputRange: ["-1deg", "1.4deg"] });
  const twistTranslateX = backgroundTwist.interpolate({ inputRange: [0, 1], outputRange: [34, -32] });
  const twistTranslateY = backgroundTwist.interpolate({ inputRange: [0, 1], outputRange: [16, -14] });
  const twistScale = backgroundTwist.interpolate({ inputRange: [0, 1], outputRange: [1.1, 1.03] });
  const twistRotate = backgroundTwist.interpolate({ inputRange: [0, 1], outputRange: ["1.5deg", "-1.2deg"] });

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <ScrollView contentContainerStyle={[styles.scrollContent, { paddingBottom: Math.max(insets.bottom, spacing.lg) }]} showsVerticalScrollIndicator={false}>
        <View style={[styles.headerShell, !isWide && styles.headerShellCompact]}>
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
                <Text style={[styles.headerCtaText, !isWide && styles.headerCtaTextCompact]}>Start free</Text>
              </Pressable>
            </View>
          </View>
        </View>

        <View style={[styles.hero, !isWide && styles.heroCompact]}>
          <Animated.Image
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
            source={require("../assets/images/landing-pulse-network.png")}
            resizeMode="cover"
            style={[
              styles.heroImage,
              !isWide && styles.heroImageCompact,
              { transform: [{ translateX: backgroundTranslateX }, { translateY: backgroundTranslateY }, { rotate: backgroundRotate }, { scale: backgroundScale }] },
            ]}
          />
          <Animated.Image
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
            source={require("../assets/images/landing-pulse-network.png")}
            resizeMode="cover"
            style={[
              styles.heroImage,
              styles.heroImageSecondary,
              !isWide && styles.heroImageCompact,
              { transform: [{ translateX: twistTranslateX }, { translateY: twistTranslateY }, { rotate: twistRotate }, { scaleX: -1 }, { scale: twistScale }] },
            ]}
          />
          <View style={[styles.heroContent, !isWide && styles.heroContentCompact]}>
            <Text
              accessibilityRole="header"
              accessibilityLabel="Recovery at home that feels clearer."
              style={[styles.heroTitle, !isWide && styles.heroTitleCompact]}
            >
              Recovery at home that
            </Text>
            <Animated.Text
              accessibilityElementsHidden
              importantForAccessibility="no-hide-descendants"
              style={[
                styles.heroPhrase,
                !isWide && styles.heroPhraseCompact,
                { opacity: phraseOpacity, transform: [{ translateY: phraseOffset }] },
              ]}
            >
              {HERO_PHRASES[phraseIndex]}
            </Animated.Text>
          </View>
        </View>

        <View style={[styles.statementBand, !isWide && styles.statementBandCompact]}>
          <Text accessibilityRole="header" style={[styles.statementText, !isWide && styles.statementTextCompact]}>
            From uncertainty to <Text style={styles.statementAccent}>one clear next step.</Text>
          </Text>
        </View>

        <View style={[styles.experienceSection, !isWide && styles.experienceSectionCompact]}>
          <View style={[styles.experienceGrid, !isWide && styles.experienceGridCompact]}>
            {[
              { title: "Check movement", preview: <QuickCheckPreview onPress={() => openAuth("start")} /> },
              { title: "Follow your plan", preview: <PlanPreview onPress={() => openAuth("start")} /> },
              { title: "See progress", preview: <ProgressPreview onPress={() => openAuth("start")} /> },
            ].map((stage, index) => (
              <Animated.View
                key={stage.title}
                style={[
                  styles.stage,
                  !isWide && styles.stageCompact,
                  {
                    opacity: stageEntries[index],
                    transform: [{
                      translateY: stageEntries[index].interpolate({ inputRange: [0, 1], outputRange: [18, 0] }),
                    }],
                  },
                ]}
              >
                <View style={styles.stageHeader}>
                  <View style={styles.stageNumber}><Text style={styles.stageNumberText}>{index + 1}</Text></View>
                  <Text style={styles.stageTitle}>{stage.title}</Text>
                  {isWide && index < 2 ? (
                    <View style={styles.stageConnector}>
                      <View style={styles.stageConnectorLine} />
                      <Ionicons name="arrow-forward" size={22} color="#AFD8B7" />
                    </View>
                  ) : null}
                </View>
                {stage.preview}
              </Animated.View>
            ))}
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

                <Text style={styles.inputLabel}>Trial code (optional)</Text>
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
                <Text style={styles.trialHint}>The trial code is optional while Rehyn is in testing.</Text>

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
  handoffScreen: { flex: 1, minHeight: 520, backgroundColor: WARM_WHITE, alignItems: "center", justifyContent: "center", gap: 30, paddingHorizontal: 24 },
  handoffCard: { width: "100%", maxWidth: 520, minHeight: 250, borderRadius: radius.lg, borderWidth: 1, borderColor: "#DADFD9", backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center", padding: 38, shadowColor: "#071E16", shadowOpacity: 0.12, shadowRadius: 24, shadowOffset: { width: 0, height: 10 } },
  handoffTitle: { color: INK, fontSize: 30, lineHeight: 38, fontWeight: "800", textAlign: "center", marginTop: 22 },
  handoffBody: { color: MUTED, fontSize: 17, lineHeight: 26, textAlign: "center", marginTop: 8, marginBottom: 24 },
  scrollContent: { flexGrow: 1 },
  headerShell: { width: "100%", backgroundColor: WARM_WHITE, paddingHorizontal: 68 },
  headerShellCompact: { paddingHorizontal: 18 },
  header: { width: "100%", maxWidth: 1400, minHeight: 86, alignSelf: "center", flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.lg },
  brandRow: { flexDirection: "row", alignItems: "center", gap: 14 },
  brandMark: { width: 56, height: 56, borderRadius: 11, backgroundColor: "#004A38", alignItems: "center", justifyContent: "center", shadowColor: "#062C20", shadowOpacity: 0.16, shadowRadius: 10, shadowOffset: { width: 0, height: 4 } },
  brandMarkCompact: { width: 44, height: 44, borderRadius: 9 },
  brandName: { color: INK, fontSize: 40, lineHeight: 46, fontWeight: "800", letterSpacing: -1.1 },
  brandNameCompact: { fontSize: 28, lineHeight: 34 },
  headerActions: { flexDirection: "row", alignItems: "center", justifyContent: "flex-end", gap: 26 },
  headerActionsCompact: { gap: 7 },
  navLink: { minHeight: 48, paddingHorizontal: 10, alignItems: "center", justifyContent: "center" },
  navLinkText: { color: "#071E17", fontSize: 18, fontWeight: "700" },
  headerCta: { minWidth: 160, minHeight: 58, paddingHorizontal: 24, borderRadius: 9, backgroundColor: DEEP_GREEN, alignItems: "center", justifyContent: "center" },
  headerCtaCompact: { minWidth: 106, minHeight: 48, paddingHorizontal: 14 },
  headerCtaText: { color: "#FFFFFF", fontSize: 20, fontWeight: "800" },
  headerCtaTextCompact: { fontSize: 16 },
  hero: { minHeight: 510, overflow: "hidden", backgroundColor: "#003E35", justifyContent: "center" },
  heroCompact: { minHeight: 390 },
  heroImage: { position: "absolute", left: "-2%", top: "-5%", width: "106%", height: "110%", opacity: 0.94 },
  heroImageSecondary: { opacity: 0.24 },
  heroImageCompact: { left: "-52%", width: "158%", opacity: 0.68 },
  heroContent: { width: "100%", maxWidth: 1400, alignSelf: "center", paddingHorizontal: 68, paddingBottom: 12 },
  heroContentCompact: { paddingHorizontal: 24, paddingBottom: 0 },
  heroTitle: { color: "#FFFFFF", maxWidth: 720, fontSize: 62, lineHeight: 70, fontWeight: "800", letterSpacing: -1.5 },
  heroTitleCompact: { maxWidth: 610, fontSize: 45, lineHeight: 53, letterSpacing: -0.8 },
  heroPhrase: { color: HERO_GREEN, maxWidth: 720, fontSize: 62, lineHeight: 72, fontWeight: "800", letterSpacing: -1.5 },
  heroPhraseCompact: { maxWidth: 610, fontSize: 45, lineHeight: 55, letterSpacing: -0.8 },
  statementBand: { minHeight: 154, backgroundColor: WARM_WHITE, alignItems: "center", justifyContent: "center", paddingHorizontal: 32, paddingVertical: 28 },
  statementBandCompact: { minHeight: 128, paddingHorizontal: 22 },
  statementText: { color: INK, fontSize: 38, lineHeight: 48, fontWeight: "800", textAlign: "center", letterSpacing: -0.8 },
  statementTextCompact: { fontSize: 29, lineHeight: 38 },
  statementAccent: { color: "#27883D" },
  experienceSection: { backgroundColor: "#003E35", paddingHorizontal: 68, paddingTop: 34, paddingBottom: 54 },
  experienceSectionCompact: { paddingHorizontal: 18, paddingTop: 28, paddingBottom: 36 },
  experienceGrid: { width: "100%", maxWidth: 1320, alignSelf: "center", flexDirection: "row", alignItems: "flex-start", gap: 30 },
  experienceGridCompact: { maxWidth: 680, flexDirection: "column", gap: 30 },
  stage: { flex: 1, minWidth: 0 },
  stageCompact: { width: "100%" },
  stageHeader: { minHeight: 42, flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 14 },
  stageNumber: { width: 32, height: 32, borderRadius: 16, backgroundColor: "#3DD45A", alignItems: "center", justifyContent: "center" },
  stageNumberText: { color: "#042F24", fontSize: 16, fontWeight: "900" },
  stageTitle: { color: "#FFFFFF", fontSize: 20, fontWeight: "800" },
  stageConnector: { flex: 1, minWidth: 28, flexDirection: "row", alignItems: "center", marginLeft: 10 },
  stageConnectorLine: { flex: 1, height: 1, backgroundColor: "#78A889", opacity: 0.65 },
  productCard: { minHeight: 270, borderRadius: 14, borderWidth: 1, borderColor: "#D8DED8", backgroundColor: WARM_WHITE, paddingHorizontal: 22, paddingTop: 20, paddingBottom: 18, shadowColor: "#001A14", shadowOpacity: 0.16, shadowRadius: 16, shadowOffset: { width: 0, height: 8 } },
  productCardPressed: { transform: [{ translateY: -2 }], borderColor: "#7FA68A" },
  previewTopline: { minHeight: 30, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 14 },
  productEyebrow: { color: INK, fontSize: 17, lineHeight: 22, fontWeight: "800" },
  productMeta: { color: MUTED, fontSize: 12, lineHeight: 18, fontWeight: "700" },
  miniProgressTrack: { height: 4, borderRadius: 2, backgroundColor: "#DCE2DC", marginTop: 12, marginBottom: 24, overflow: "hidden" },
  miniProgressFill: { width: "29%", height: "100%", borderRadius: 2, backgroundColor: "#2AA348" },
  productQuestion: { color: "#10251E", fontSize: 21, lineHeight: 27, fontWeight: "800", maxWidth: 310, marginBottom: 8 },
  productSupporting: { color: MUTED, fontSize: 14, lineHeight: 20 },
  choiceRow: { flexDirection: "row", gap: 9, marginTop: 18 },
  choiceTile: { flex: 1, minHeight: 62, borderRadius: 10, borderWidth: 1, borderColor: "#D2D9D3", backgroundColor: "#FFFFFF", flexDirection: "row", alignItems: "center", gap: 7, paddingHorizontal: 10 },
  choiceTileSelected: { borderColor: "#5A8A68", backgroundColor: "#E8F0E9" },
  choiceText: { flex: 1, minWidth: 0, color: INK, fontSize: 13, fontWeight: "800" },
  planContent: { flexDirection: "row", alignItems: "center", gap: 18, marginTop: 24, marginBottom: 22 },
  exerciseIllustration: { width: 92, height: 92, borderRadius: 46, backgroundColor: "#DCE9DE", alignItems: "center", justifyContent: "center" },
  exerciseCopy: { flex: 1, minWidth: 0 },
  exerciseTitle: { color: INK, fontSize: 20, lineHeight: 27, fontWeight: "800", marginBottom: 6 },
  productButton: { minHeight: 52, borderRadius: 9, backgroundColor: DEEP_GREEN, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 9, paddingHorizontal: 18 },
  productButtonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
  previewFilter: { flexDirection: "row", alignItems: "center", gap: 4, borderRadius: radius.pill, backgroundColor: "#E7EEE7", paddingHorizontal: 10, paddingVertical: 6 },
  previewFilterText: { color: DEEP_GREEN, fontSize: 11, fontWeight: "800" },
  progressMessage: { color: INK, fontSize: 14, lineHeight: 20, fontWeight: "700", marginTop: 10, marginBottom: 1 },
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
