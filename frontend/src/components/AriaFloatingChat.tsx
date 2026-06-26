import { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, Animated, Easing, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { createAudioPlayer } from "expo-audio";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { authedFetch } from "@/src/auth";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

type Props = {
  /** Pixels from the bottom of the screen, above the sticky CTA bar. Defaults to 100. */
  bottomOffset?: number;
};

/**
 * A floating Aria avatar fixed in the lower-right corner. After a short delay it
 * pops up a speech bubble with a personalized caring message, optionally with
 * voice. Tap the avatar (or bubble) → open the Aria chat tab. Tap the close
 * icon → just dismiss the bubble for this session, the avatar stays.
 */
export default function AriaFloatingChat({ bottomOffset = 100 }: Props) {
  const router = useRouter();
  const [bubble, setBubble] = useState<string | null>(null);
  const [messages, setMessages] = useState<string[]>([]);
  const [shown, setShown] = useState(false);
  const fade = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0.6)).current;
  const greetedRef = useRef(false);
  const idxRef = useRef(0);

  const playVoice = async (text: string) => {
    if (Platform.OS === "web") return; // most web browsers block autoplay audio
    try {
      const r = await fetch(`${BASE}/api/tts/generate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!r.ok) return;
      const d = await r.json();
      const player = createAudioPlayer({ uri: `data:audio/mpeg;base64,${d.audio_b64}` });
      player.play();
    } catch {/* */}
  };

  const showBubble = (text: string, withVoice = false) => {
    setBubble(text);
    setShown(true);
    Animated.parallel([
      Animated.timing(fade, { toValue: 1, duration: 350, useNativeDriver: true, easing: Easing.out(Easing.ease) }),
      Animated.spring(scale, { toValue: 1, friction: 7, useNativeDriver: true }),
    ]).start();
    if (withVoice) playVoice(text);
  };

  const hideBubble = () => {
    Animated.timing(fade, { toValue: 0, duration: 250, useNativeDriver: true }).start(() => {
      setShown(false);
      setBubble(null);
    });
  };

  // Load proactive messages and greet after ~2 seconds.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await authedFetch("/api/chat/proactive/messages?n=5");
        const d = await r.json();
        if (cancelled) return;
        const arr: string[] = d.messages || ["How are you?"];
        setMessages(arr);
        // First-show: greet with voice
        const t = setTimeout(() => {
          if (cancelled || greetedRef.current) return;
          greetedRef.current = true;
          showBubble(arr[0], true);
          // Auto-cycle a random other message every 25s, no voice
          const cycle = setInterval(() => {
            idxRef.current = (idxRef.current + 1) % arr.length;
            showBubble(arr[idxRef.current], false);
          }, 25000);
          // Auto-dismiss the FIRST bubble after 12s; subsequent cycles also auto-dismiss
          const autoDismiss = setInterval(() => hideBubble(), 12000);
          // Cleanup intervals on unmount via greetedRef ref (we just live as long as the page)
          return () => { clearInterval(cycle); clearInterval(autoDismiss); };
        }, 2000);
        return () => clearTimeout(t);
      } catch {/* offline / not signed in */}
    })();
    return () => { cancelled = true; };
  }, []);

  const onAvatarPress = () => {
    Haptics.selectionAsync();
    router.push("/(tabs)/chat");
  };

  return (
    <View pointerEvents="box-none" style={[styles.wrap, { bottom: bottomOffset }]}>
      {shown && bubble && (
        <Animated.View style={[styles.bubbleWrap, { opacity: fade, transform: [{ scale }] }]}>
          <Pressable onPress={onAvatarPress} style={styles.bubble} testID="aria-floating-bubble">
            <Text style={styles.bubbleText} numberOfLines={3}>{bubble}</Text>
          </Pressable>
          <Pressable onPress={hideBubble} hitSlop={8} style={styles.close} testID="aria-floating-close">
            <Ionicons name="close" size={14} color={colors.onSurfaceTertiary} />
          </Pressable>
          <View style={styles.bubbleTail} />
        </Animated.View>
      )}
      <Pressable onPress={onAvatarPress} style={({ pressed }) => [styles.fab, pressed && { opacity: 0.9 }]} testID="aria-fab">
        <Ionicons name="heart" size={26} color="#fff" />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: "absolute",
    right: spacing.md,
    alignItems: "flex-end",
  },
  fab: {
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  bubbleWrap: {
    marginBottom: spacing.sm,
    maxWidth: 250,
    alignSelf: "flex-end",
  },
  bubble: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.divider,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    paddingRight: spacing.md + 14,
    shadowColor: "#000",
    shadowOpacity: 0.12,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 5,
  },
  bubbleText: {
    color: colors.onSurface,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "500",
  },
  bubbleTail: {
    position: "absolute",
    right: 16,
    bottom: -7,
    width: 14,
    height: 14,
    backgroundColor: colors.surface,
    borderRightWidth: 1,
    borderBottomWidth: 1,
    borderColor: colors.divider,
    transform: [{ rotate: "45deg" }],
  },
  close: {
    position: "absolute",
    top: 6,
    right: 6,
    width: 18,
    height: 18,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 9,
  },
});
