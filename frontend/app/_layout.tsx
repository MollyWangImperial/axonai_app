import { Stack, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { LogBox } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { getCachedUser, authedFetch, cachePatientOnboarding, onboardingCompleteKey, recoverSingleAccountCache, hasAcceptedConsent } from "@/src/auth";
import { preloadAssessmentMediaPipe } from "@/src/assessmentPreload";
import { storage } from "@/src/utils/storage";
import { DisplayPreferencesProvider, useDisplayPreferences } from "@/src/displayPreferences";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();

function AuthGate() {
  const router = useRouter();
  const segments = useSegments();
  useEffect(() => {
    (async () => {
      const u = await getCachedUser();
      const seg0 = segments[0] || "";
      // Public routes that should be reachable without auth (e.g., legal pages linked from sign-in footer).
      const publicRoutes = ["sign-in", "privacy-policy"];
      // If not signed in and not on a public route, redirect
      if (!u && !publicRoutes.includes(seg0)) {
        router.replace("/sign-in");
        return;
      }
      if (!u) return;
      if (u.role !== "therapist") {
        void preloadAssessmentMediaPipe();
      }
      // Therapist role → therapist portal
      if (u.role === "therapist" && seg0 !== "therapist" && !publicRoutes.includes(seg0)) {
        router.replace("/therapist");
        return;
      }
      // Patient role → ensure onboarding is complete before entering main app
      if (u.role !== "therapist") {
        await recoverSingleAccountCache(u.id);
        // Safety/consent gate: new patients must accept the disclaimer first.
        const consentOk = await hasAcceptedConsent(u.id);
        if (!consentOk && seg0 !== "consent" && !publicRoutes.includes(seg0)) {
          router.replace("/consent");
          return;
        }
        const localFlag = await storage.getItem(onboardingCompleteKey(u.id), "");
        const allowedDuringOnboarding = ["onboarding", "sign-in", "consent", "privacy-policy"];
        if (!localFlag && !allowedDuringOnboarding.includes(seg0)) {
          // double-check with backend (in case user signed in on a fresh device)
          try {
            const r = await authedFetch("/api/users/onboarding");
            const j = await r.json();
            if (j.onboarding_complete) {
              await cachePatientOnboarding(u.id, j.profile);
            } else {
              router.replace("/onboarding");
            }
          } catch {
            router.replace("/onboarding");
          }
        }
      }
    })();
  }, [segments.join("/")]);
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
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: palette.page } }} />
    </>
  );
}
