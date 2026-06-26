import { Stack, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect, useState } from "react";
import { LogBox } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { getCachedUser } from "@/src/auth";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();

function AuthGate() {
  const router = useRouter();
  const segments = useSegments();
  useEffect(() => {
    (async () => {
      const u = await getCachedUser();
      const seg0 = segments[0] || "";
      // If not signed in and not already on sign-in, redirect
      if (!u && seg0 !== "sign-in") {
        router.replace("/sign-in");
      } else if (u && u.role === "therapist" && seg0 !== "therapist" && seg0 !== "sign-in") {
        router.replace("/therapist");
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
        <AuthGate />
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: "#FDFDFD" } }} />
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
