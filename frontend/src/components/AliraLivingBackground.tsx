import { useEffect, useRef, useState } from "react";
import { AccessibilityInfo, Animated, Easing, StyleSheet, View } from "react-native";

type Props = {
  darkMode: boolean;
  engaged?: boolean;
};

export default function AliraLivingBackground({ darkMode, engaged = false }: Props) {
  const breath = useRef(new Animated.Value(0)).current;
  const drift = useRef(new Animated.Value(0)).current;
  const [reduceMotion, setReduceMotion] = useState(false);

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
      breath.setValue(0.35);
      drift.setValue(0);
      return;
    }

    const breathingLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(breath, {
          toValue: 1,
          duration: engaged ? 3600 : 5200,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(breath, {
          toValue: 0,
          duration: engaged ? 3600 : 5200,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );
    const driftingLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(drift, {
          toValue: 1,
          duration: 13000,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.timing(drift, {
          toValue: 0,
          duration: 13000,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
      ]),
    );

    breathingLoop.start();
    driftingLoop.start();
    return () => {
      breathingLoop.stop();
      driftingLoop.stop();
    };
  }, [breath, drift, engaged, reduceMotion]);

  const washOpacity = breath.interpolate({
    inputRange: [0, 1],
    outputRange: darkMode ? [0.14, 0.24] : [0.28, 0.46],
  });
  const contourOpacity = breath.interpolate({
    inputRange: [0, 1],
    outputRange: engaged ? [0.28, 0.58] : [0.18, 0.38],
  });
  const contourScale = breath.interpolate({ inputRange: [0, 1], outputRange: [0.985, 1.025] });
  const driftX = drift.interpolate({ inputRange: [0, 1], outputRange: [-18, 24] });
  const driftY = drift.interpolate({ inputRange: [0, 1], outputRange: [-5, 9] });

  const traceColor = darkMode ? "rgba(129, 187, 145, 0.22)" : "rgba(74, 120, 86, 0.16)";
  const contourColor = darkMode ? "rgba(129, 187, 145, 0.22)" : "rgba(74, 120, 86, 0.17)";

  return (
    <View
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={styles.layer}
      testID="alira-living-background"
    >
      <Animated.View
        style={[
          StyleSheet.absoluteFill,
          { backgroundColor: darkMode ? "#173026" : "#E8F0E9", opacity: washOpacity },
        ]}
      />

      <Animated.View
        style={[
          styles.contour,
          styles.contourTop,
          {
            borderColor: contourColor,
            opacity: contourOpacity,
            transform: [{ scale: contourScale }, { translateX: driftX }],
          },
        ]}
      >
        <View style={[styles.contourInner, { borderColor: contourColor }]} />
      </Animated.View>

      <Animated.View
        style={[
          styles.contour,
          styles.contourBottom,
          {
            borderColor: contourColor,
            opacity: contourOpacity,
            transform: [{ scale: contourScale }, { translateX: Animated.multiply(driftX, -0.55) }],
          },
        ]}
      />

      <Animated.View style={[styles.trace, styles.traceOne, { backgroundColor: traceColor, transform: [{ translateX: driftX }, { translateY: driftY }, { rotate: "-7deg" }] }]} />
      <Animated.View style={[styles.trace, styles.traceTwo, { backgroundColor: traceColor, transform: [{ translateX: Animated.multiply(driftX, -0.7) }, { translateY: Animated.multiply(driftY, -0.5) }, { rotate: "5deg" }] }]} />
      <Animated.View style={[styles.trace, styles.traceThree, { backgroundColor: traceColor, opacity: contourOpacity, transform: [{ translateX: Animated.multiply(driftX, 0.45) }, { rotate: "-3deg" }] }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  layer: {
    ...StyleSheet.absoluteFillObject,
    overflow: "hidden",
  },
  contour: {
    position: "absolute",
    width: 620,
    height: 270,
    borderWidth: 1,
    borderRadius: 135,
  },
  contourTop: {
    top: 86,
    right: -245,
  },
  contourBottom: {
    bottom: 92,
    left: -330,
  },
  contourInner: {
    position: "absolute",
    top: 24,
    right: 24,
    bottom: 24,
    left: 24,
    borderWidth: 1,
    borderRadius: 110,
  },
  trace: {
    position: "absolute",
    left: "-18%",
    width: "136%",
    height: 1,
  },
  traceOne: { top: "34%" },
  traceTwo: { top: "57%" },
  traceThree: { top: "78%" },
});
