import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Appearance, Platform, StyleSheet, View } from "react-native";

import {
  DEFAULT_USER_PREFERENCES,
  loadUserPreferences,
  subscribeUserPreferences,
  textScaleFor,
  UserPreferences,
} from "@/src/userPreferences";

export type DisplayPalette = {
  page: string;
  surface: string;
  soft: string;
  text: string;
  muted: string;
  border: string;
  brand: string;
  onBrand: string;
};

const LIGHT_PALETTE: DisplayPalette = {
  page: "#F4F6F4",
  surface: "#FAFBFA",
  soft: "#E9EFEB",
  text: "#183A32",
  muted: "#53635C",
  border: "#D8DFDA",
  brand: "#2F754D",
  onBrand: "#FFFFFF",
};

const DARK_PALETTE: DisplayPalette = {
  page: "#0F1D18",
  surface: "#182A23",
  soft: "#22382F",
  text: "#F2F7F4",
  muted: "#B7C8C0",
  border: "#365046",
  brand: "#78B58A",
  onBrand: "#0E1B16",
};

type DisplayPreferencesValue = {
  preferences: UserPreferences;
  palette: DisplayPalette;
  scale: number;
};

const DisplayPreferencesContext = createContext<DisplayPreferencesValue>({
  preferences: DEFAULT_USER_PREFERENCES,
  palette: LIGHT_PALETTE,
  scale: 1,
});

export function DisplayPreferencesProvider({ children }: { children: React.ReactNode }) {
  const [preferences, setPreferences] = useState(DEFAULT_USER_PREFERENCES);

  useEffect(() => {
    let active = true;
    void loadUserPreferences().then((saved) => {
      if (active) setPreferences(saved);
    });
    const unsubscribe = subscribeUserPreferences((saved) => {
      if (active) setPreferences(saved);
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    const scheme = preferences.darkMode ? "dark" : "light";
    if (Platform.OS === "web") {
      document.documentElement.style.colorScheme = scheme;
      document.documentElement.style.backgroundColor = preferences.darkMode ? DARK_PALETTE.page : LIGHT_PALETTE.page;
      document.body.style.backgroundColor = preferences.darkMode ? DARK_PALETTE.page : LIGHT_PALETTE.page;
    } else {
      Appearance.setColorScheme(scheme);
    }
  }, [preferences.darkMode]);

  const palette = preferences.darkMode ? DARK_PALETTE : LIGHT_PALETTE;
  const scale = textScaleFor(preferences.textSize);
  const brightnessDim = Math.min(0.2, Math.max(0, (100 - preferences.brightness) / 100) * 0.66);
  const unthemedDarkDim = preferences.darkMode ? 0.08 : 0;
  const dimOpacity = Math.min(0.24, brightnessDim + unthemedDarkDim);
  const value = useMemo(() => ({ preferences, palette, scale }), [palette, preferences, scale]);

  return (
    <DisplayPreferencesContext.Provider value={value}>
      <View style={[styles.root, { backgroundColor: palette.page }]}>
        {children}
        {dimOpacity > 0.005 ? (
          <View
            testID="display-brightness-overlay"
            pointerEvents="none"
            style={[styles.dimmer, { backgroundColor: `rgba(4, 14, 10, ${dimOpacity})` }]}
          />
        ) : null}
      </View>
    </DisplayPreferencesContext.Provider>
  );
}

export function useDisplayPreferences() {
  return useContext(DisplayPreferencesContext);
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  dimmer: { ...StyleSheet.absoluteFillObject, zIndex: 9999 },
});
