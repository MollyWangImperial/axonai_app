import { useEffect, useRef } from "react";
import { View, StyleSheet, Animated, Easing } from "react-native";
import { colors, spacing, radius } from "@/src/theme";

/**
 * Three pulsing dots in an assistant bubble — mirrors iMessage / WhatsApp
 * "the other person is typing" pattern. Drop this in the chat list while
 * waiting on the assistant reply.
 */
export default function TypingIndicator() {
  const dot1 = useRef(new Animated.Value(0.3)).current;
  const dot2 = useRef(new Animated.Value(0.3)).current;
  const dot3 = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const animate = (dot: Animated.Value, delay: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(dot, { toValue: 1, duration: 380, delay, useNativeDriver: true, easing: Easing.inOut(Easing.ease) }),
          Animated.timing(dot, { toValue: 0.3, duration: 380, useNativeDriver: true, easing: Easing.inOut(Easing.ease) }),
        ])
      );
    const a1 = animate(dot1, 0);
    const a2 = animate(dot2, 140);
    const a3 = animate(dot3, 280);
    a1.start();
    a2.start();
    a3.start();
    return () => {
      a1.stop(); a2.stop(); a3.stop();
    };
  }, [dot1, dot2, dot3]);

  return (
    <View style={styles.bubble} testID="typing-indicator">
      <Animated.View style={[styles.dot, { opacity: dot1, transform: [{ scale: dot1 }] }]} />
      <Animated.View style={[styles.dot, { opacity: dot2, transform: [{ scale: dot2 }] }]} />
      <Animated.View style={[styles.dot, { opacity: dot3, transform: [{ scale: dot3 }] }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  bubble: {
    alignSelf: "flex-start",
    flexDirection: "row",
    gap: 5,
    backgroundColor: colors.surfaceSecondary,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: radius.lg,
    borderBottomLeftRadius: 4,
    alignItems: "center",
    minWidth: 56,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.brandPrimary,
  },
});
