import { useEffect, useRef } from "react";
import { Animated, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

// A small congratulations toast for earned points: it pops in over the
// screen, holds for a moment, and fades out on its own - no tap needed.

export type PointsCelebrationEvent = {
  points: number;
  message?: string;
  key: number; // unique per event (e.g. Date.now()) so repeats re-animate
};

export function celebrationEvent(points: number, message?: string): PointsCelebrationEvent {
  return { points, message, key: Date.now() };
}

export function PointsCelebration({
  event,
  onDone,
}: {
  event: PointsCelebrationEvent | null;
  onDone: () => void;
}) {
  const opacity = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0.85)).current;
  const translateY = useRef(new Animated.Value(10)).current;

  useEffect(() => {
    if (!event) return;
    opacity.setValue(0);
    scale.setValue(0.85);
    translateY.setValue(10);
    const animation = Animated.sequence([
      Animated.parallel([
        Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
        Animated.spring(scale, { toValue: 1, friction: 6, useNativeDriver: true }),
        Animated.timing(translateY, { toValue: 0, duration: 200, useNativeDriver: true }),
      ]),
      Animated.delay(1400),
      Animated.timing(opacity, { toValue: 0, duration: 450, useNativeDriver: true }),
    ]);
    animation.start(({ finished }) => { if (finished) onDone(); });
    return () => animation.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [event?.key]);

  if (!event) return null;

  return (
    <View pointerEvents="none" style={styles.overlay} testID="points-celebration">
      <Animated.View style={[styles.card, { opacity, transform: [{ scale }, { translateY }] }]}>
        <View style={styles.iconCircle}>
          <Ionicons name="ribbon" size={30} color="#B8860B" />
        </View>
        <Text style={styles.points}>+{event.points} point{event.points === 1 ? "" : "s"}</Text>
        <Text style={styles.message}>{event.message || "Well done - every step counts!"}</Text>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 50,
    elevation: 50,
  },
  card: {
    alignItems: "center",
    gap: 6,
    minWidth: 220,
    maxWidth: 320,
    paddingHorizontal: 28,
    paddingVertical: 22,
    borderRadius: 20,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#D9E4DC",
    shadowColor: "#12331F",
    shadowOpacity: 0.18,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 8 },
  },
  iconCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#FFF3D0",
  },
  points: { fontSize: 26, lineHeight: 32, fontWeight: "900", color: "#155D3C" },
  message: { fontSize: 14, lineHeight: 20, fontWeight: "700", color: "#3A4A40", textAlign: "center" },
});
