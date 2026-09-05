import { useEffect, useRef } from "react";
import {
  Animated,
  Easing,
  Image,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useAudioPlayer } from "expo-audio";
import * as Haptics from "expo-haptics";

import { useDisplayPreferences } from "@/src/displayPreferences";
import { radius, spacing } from "@/src/theme";

const medalImage = require("../../assets/images/rewards/100-point-medal.png");
const celebrationFanfare = require("../../assets/audio/rewards/100-point-fanfare.wav");

type HundredPointCelebrationProps = {
  visible: boolean;
  name: string;
  points: number;
  onClose: () => void;
};

export function HundredPointCelebration({ visible, name, points, onClose }: HundredPointCelebrationProps) {
  const { width } = useWindowDimensions();
  const { palette } = useDisplayPreferences();
  const compact = width < 720;
  const fanfare = useAudioPlayer(celebrationFanfare);
  const backdropOpacity = useRef(new Animated.Value(0)).current;
  const panelOpacity = useRef(new Animated.Value(0)).current;
  const panelScale = useRef(new Animated.Value(0.94)).current;
  const medalOpacity = useRef(new Animated.Value(0)).current;
  const medalScale = useRef(new Animated.Value(0.52)).current;
  const medalLift = useRef(new Animated.Value(28)).current;
  const ringPulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!visible) {
      fanfare.pause();
      void fanfare.seekTo(0).catch(() => undefined);
      return;
    }

    backdropOpacity.setValue(0);
    panelOpacity.setValue(0);
    panelScale.setValue(0.94);
    medalOpacity.setValue(0);
    medalScale.setValue(0.52);
    medalLift.setValue(28);
    ringPulse.setValue(0);

    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => undefined);
    try {
      fanfare.play();
    } catch {
      // Some browsers block non-gesture audio; the visual award still appears.
    }

    const entrance = Animated.sequence([
      Animated.parallel([
        Animated.timing(backdropOpacity, { toValue: 1, duration: 420, easing: Easing.out(Easing.ease), useNativeDriver: true }),
        Animated.timing(panelOpacity, { toValue: 1, duration: 520, easing: Easing.out(Easing.ease), useNativeDriver: true }),
        Animated.timing(panelScale, { toValue: 1, duration: 620, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
      ]),
      Animated.parallel([
        Animated.timing(medalOpacity, { toValue: 1, duration: 520, easing: Easing.out(Easing.ease), useNativeDriver: true }),
        Animated.spring(medalScale, { toValue: 1, friction: 6, tension: 46, useNativeDriver: true }),
        Animated.timing(medalLift, { toValue: 0, duration: 720, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
      ]),
    ]);
    const pulse = Animated.loop(Animated.sequence([
      Animated.timing(ringPulse, { toValue: 1, duration: 1150, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      Animated.timing(ringPulse, { toValue: 0, duration: 1150, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
    ]));
    entrance.start();
    pulse.start();
    return () => {
      entrance.stop();
      pulse.stop();
    };
  }, [backdropOpacity, fanfare, medalLift, medalOpacity, medalScale, panelOpacity, panelScale, ringPulse, visible]);

  const ringScale = ringPulse.interpolate({ inputRange: [0, 1], outputRange: [0.92, 1.08] });
  const ringOpacity = ringPulse.interpolate({ inputRange: [0, 1], outputRange: [0.24, 0.62] });
  const displayName = name.trim() || "there";

  return (
    <Modal visible={visible} transparent animationType="none" onRequestClose={onClose}>
      <Animated.View style={[styles.backdrop, { opacity: backdropOpacity }]}>
        <Animated.View
          accessibilityRole="alert"
          accessibilityLabel={`Wonderful work, ${displayName}. You reached ${points} points.`}
          testID="hundred-point-celebration"
          style={[
            styles.card,
            compact && styles.cardCompact,
            { backgroundColor: palette.surface, opacity: panelOpacity, transform: [{ scale: panelScale }] },
          ]}
        >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close 100 point celebration"
            testID="hundred-point-close"
            onPress={onClose}
            style={({ pressed }) => [styles.closeButton, { backgroundColor: palette.soft }, pressed && styles.pressed]}
          >
            <Ionicons name="close" size={26} color={palette.text} />
          </Pressable>

          <View style={[styles.medalStage, compact && styles.medalStageCompact]}>
            <Animated.View
              style={[
                styles.ring,
                compact && styles.ringCompact,
                { borderColor: palette.brand, opacity: ringOpacity, transform: [{ scale: ringScale }] },
              ]}
            />
            <Animated.View style={{ opacity: medalOpacity, transform: [{ translateY: medalLift }, { scale: medalScale }] }}>
              <Image
                accessibilityLabel="Gold and green Rehyn 100 point medal"
                source={medalImage}
                resizeMode="contain"
                style={[styles.medal, compact && styles.medalCompact]}
              />
            </Animated.View>
          </View>

          <View style={[styles.copy, compact && styles.copyCompact]}>
            <Text style={[styles.kicker, { color: palette.brand }]}>100 POINT MILESTONE</Text>
            <Text style={[styles.title, { color: palette.text }]}>Wonderful work, {displayName}!</Text>
            <Text style={[styles.body, { color: palette.muted }]}>You reached {points} points. Your steady effort has earned this medal.</Text>
            <Pressable
              accessibilityRole="button"
              testID="hundred-point-continue"
              onPress={onClose}
              style={({ pressed }) => [styles.continueButton, { backgroundColor: palette.brand }, pressed && styles.pressed]}
            >
              <Text style={styles.continueText}>Continue</Text>
            </Pressable>
          </View>
        </Animated.View>
      </Animated.View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.lg,
    backgroundColor: "rgba(12, 34, 27, 0.62)",
  },
  card: {
    width: "100%",
    maxWidth: 980,
    minHeight: 410,
    borderRadius: radius.md,
    flexDirection: "row",
    alignItems: "center",
    overflow: "hidden",
    shadowColor: "#0B251B",
    shadowOpacity: 0.28,
    shadowRadius: 32,
    shadowOffset: { width: 0, height: 18 },
    elevation: 24,
  },
  cardCompact: { minHeight: 0, flexDirection: "column", paddingTop: spacing.xl },
  closeButton: {
    position: "absolute",
    zIndex: 4,
    top: spacing.md,
    right: spacing.md,
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: "center",
    justifyContent: "center",
  },
  medalStage: { width: "47%", minHeight: 410, alignItems: "center", justifyContent: "center" },
  medalStageCompact: { width: "100%", minHeight: 250 },
  ring: { position: "absolute", width: 340, height: 340, borderRadius: 170, borderWidth: 2 },
  ringCompact: { width: 225, height: 225, borderRadius: 113 },
  medal: { width: 360, height: 390 },
  medalCompact: { width: 230, height: 250 },
  copy: { width: "53%", paddingTop: 72, paddingRight: 64, paddingBottom: 56, paddingLeft: spacing.md },
  copyCompact: { width: "100%", paddingTop: 0, paddingHorizontal: spacing.lg, paddingBottom: spacing.xl, alignItems: "center" },
  kicker: { fontSize: 13, lineHeight: 18, fontWeight: "900" },
  title: { marginTop: spacing.sm, fontSize: 34, lineHeight: 41, fontWeight: "900", textAlign: "left" },
  body: { marginTop: spacing.sm, fontSize: 19, lineHeight: 28, fontWeight: "500" },
  continueButton: { width: "100%", minHeight: 60, marginTop: spacing.xl, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  continueText: { color: "#FFFFFF", fontSize: 18, lineHeight: 24, fontWeight: "900" },
  pressed: { opacity: 0.82 },
});
