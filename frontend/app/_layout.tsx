import { Stack, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import * as Notifications from "expo-notifications";
import { useEffect, useRef } from "react";
import { LogBox, Platform } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { getCachedUser, authedFetch, cachePatientOnboarding, onboardingCompleteKey, recoverSingleAccountCache, hasAcceptedConsent, hasPendingConsent, clearPendingConsent, setConsentAccepted } from "@/src/auth";
import { preloadAssessmentMediaPipe } from "@/src/assessmentPreload";
import { storage } from "@/src/utils/storage";
import { DisplayPreferencesProvider, useDisplayPreferences } from "@/src/displayPreferences";
import { FAST_ACTION_ID, initializeNotificationActions } from "@/src/utils/notifications";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();

function AuthGate() {
  const router = useRouter();
  const segments = useSegments();
  const seg0 = segments[0] || "";
  useEffect(() => {
    (async () => {
      const u = await getCachedUser();
      // Only the sign-in screen and its privacy notice are available before authentication.
      const unauthenticatedRoutes = ["sign-in", "privacy-policy"];
      const signedInLegalRoutes = ["sign-in", "consent", "privacy-policy", "terms-of-use", "data-permissions", "movement-videos"];
      if (!u && !unauthenticatedRoutes.includes(seg0)) {
        router.replace("/sign-in");
        return;
      }
      if (!u) return;
      if (u.role !== "therapist") {
        void preloadAssessmentMediaPipe();
      }
      // Therapist role → therapist portal
      if (u.role === "therapist" && seg0 !== "therapist" && !signedInLegalRoutes.includes(seg0)) {
        router.replace("/therapist");
        return;
      }
      // Patient role → ensure onboarding is complete before entering main app
      if (u.role !== "therapist") {
        await recoverSingleAccountCache(u.id);
        // Terms gate: only an account that has not yet accepted the current
        // Terms (a new account) is sent to the consent screen. Acceptance is
        // stored on the account in MongoDB and seeded locally at sign-in, so a
        // returning patient is never shown the Terms again.
        let consentOk = await hasAcceptedConsent(u.id);
        if (consentOk) {
          await clearPendingConsent();
        } else if (await hasPendingConsent()) {
          try {
            await setConsentAccepted(u.id);
            await clearPendingConsent();
            consentOk = true;
          } catch {
            consentOk = false;
          }
        }
        if (!consentOk && seg0 !== "consent" && !signedInLegalRoutes.includes(seg0)) {
          router.replace("/consent");
          return;
        }
        if (consentOk && seg0 === "consent") {
          // Already accepted (e.g. restored from the account record): skip the screen.
          router.replace("/");
          return;
        }
        // Initial survey gate: the device flag is seeded from the account record
        // at sign-in; if it is missing, ask the backend and only start the survey
        // when the account really has not completed it. A failed request never
        // restarts the survey for a patient who already answered it.
        const localFlag = await storage.getItem(onboardingCompleteKey(u.id), "");
        const allowedDuringOnboarding = ["onboarding", ...signedInLegalRoutes];
        if (!localFlag && !allowedDuringOnboarding.includes(seg0)) {
          try {
            const r = await authedFetch("/api/users/onboarding");
            if (r.ok) {
              const j = await r.json();
              if (j.onboarding_complete) {
                await cachePatientOnboarding(u.id, j.profile);
              } else {
                router.replace("/onboarding");
              }
            }
          } catch {
            // Backend unreachable: keep the current screen; the next navigation re-checks.
          }
        }
      }
    })();
  }, [router, seg0]);
  return null;
}

function NotificationRouteHandler() {
  const router = useRouter();
  const handledResponseId = useRef("");

  useEffect(() => {
    if (Platform.OS === "web") return;
    void initializeNotificationActions();
    const openResponse = (response: Notifications.NotificationResponse | null) => {
      if (!response) return;
      const responseId = `${response.notification.request.identifier}:${response.actionIdentifier}`;
      if (handledResponseId.current === responseId) return;
      handledResponseId.current = responseId;
      const dataRoute = response.notification.request.content.data?.route;
      const route = response.actionIdentifier === FAST_ACTION_ID ? "/emergency" : dataRoute;
      if (route === "/emergency" || route === "/chat" || route === "/") {
        router.push(route as never);
      }
    };

    void Notifications.getLastNotificationResponseAsync().then(openResponse);
    const subscription = Notifications.addNotificationResponseReceivedListener(openResponse);
    return () => subscription.remove();
  }, [router]);

  return null;
}

export default function RootLayout() {
  const [loaded, error] = useIconFonts();

  useEffect(() => {
    if (loaded || error) {
      SplashScreen.hideAsync();
    }
  }, [loaded, error]);

  if (!loaded && !error) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <DisplayPreferencesProvider>
          <AppStack />
        </DisplayPreferencesProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

function AppStack() {
  const { palette } = useDisplayPreferences();
  return (
    <>
      <AuthGate />
      <NotificationRouteHandler />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: palette.page } }} />
    </>
  );
}
