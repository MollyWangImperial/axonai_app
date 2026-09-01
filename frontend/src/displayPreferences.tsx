import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Appearance, Platform, StyleSheet, View } from "react-native";

import {
  DEFAULT_USER_PREFERENCES,
  loadUserPreferences,
  subscribeUserPreferences,
  textScaleFor,
  UserPreferences,
} from "@/src/userPreferences";
import { subscribeAuthState } from "@/src/auth";

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

// Dark mode is a neutral dark grey, not a dark green: the grey ground stays
// out of the way of photos and lets the green branding read as the accent.
// The two anchor palettes below are the softest and deepest ends of the
// user's "Dark mode depth" slider; darkPaletteFor() blends between them.
const DARK_SOFT_ANCHOR = {
  page: "#454A4F",
  surface: "#4D5257",
  soft: "#585E64",
  border: "#70777E",
};

const DARK_DEEP_ANCHOR = {
  page: "#0A0B0D",
  surface: "#121417",
  soft: "#1B1E22",
  border: "#2E3338",
};

function mixHex(from: string, to: string, t: number) {
  const channel = (offset: number) => {
    const a = parseInt(from.slice(offset, offset + 2), 16);
    const b = parseInt(to.slice(offset, offset + 2), 16);
    return Math.round(a + (b - a) * t).toString(16).padStart(2, "0");
  };
  return `#${channel(1)}${channel(3)}${channel(5)}`;
}

export function darkPaletteFor(darkness: number): DisplayPalette {
  const t = Math.max(0, Math.min(100, Number.isFinite(darkness) ? darkness : 55)) / 100;
  return {
    page: mixHex(DARK_SOFT_ANCHOR.page, DARK_DEEP_ANCHOR.page, t),
    surface: mixHex(DARK_SOFT_ANCHOR.surface, DARK_DEEP_ANCHOR.surface, t),
    soft: mixHex(DARK_SOFT_ANCHOR.soft, DARK_DEEP_ANCHOR.soft, t),
    text: "#F2F4F3",
    muted: "#C2C7C4",
    border: mixHex(DARK_SOFT_ANCHOR.border, DARK_DEEP_ANCHOR.border, t),
    brand: "#96D7A8",
    onBrand: "#101512",
  };
}

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
    const reloadPreferences = () => void loadUserPreferences().then((saved) => {
      if (active) setPreferences(saved);
    });
    reloadPreferences();
    const unsubscribe = subscribeUserPreferences((saved) => {
      if (active) setPreferences(saved);
    });
    const unsubscribeAuth = subscribeAuthState(reloadPreferences);
    return () => {
      active = false;
      unsubscribe();
      unsubscribeAuth();
    };
  }, []);

  const palette = useMemo(
    () => (preferences.darkMode ? darkPaletteFor(preferences.darkness) : LIGHT_PALETTE),
    [preferences.darkMode, preferences.darkness],
  );

  useEffect(() => {
    const scheme = preferences.darkMode ? "dark" : "light";
    if (Platform.OS === "web") {
      document.documentElement.style.colorScheme = scheme;
      document.documentElement.style.backgroundColor = palette.page;
      document.body.style.backgroundColor = palette.page;
    } else {
      Appearance.setColorScheme(scheme);
    }
  }, [preferences.darkMode, palette.page]);

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
