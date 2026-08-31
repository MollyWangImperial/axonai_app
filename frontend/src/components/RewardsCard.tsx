import { useCallback, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { authedFetch } from "@/src/auth";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import { colors, radius, spacing } from "@/src/theme";

// Encouragement display (spec section 10): points reward effort and safe
// participation, medals mark persistence, and streaks come with freezes so a
// rest day, fatigue, or illness never reads as failure.

type Medal = { id: string; name: string; threshold: number; earned: boolean; progress: number };
type Rewards = {
  points: number;
  message: string;
  streak: { current_days: number; frozen_days_used: number; freezes_explained: string };
  medals: Medal[];
  next_medal: Medal | null;
};

export function RewardsCard() {
  const { palette } = useDisplayPreferences();
  const cached = getScreenCache<Rewards>("rewards");
  const [rewards, setRewards] = useState<Rewards | null>(cached ?? null);

  const load = useCallback(async () => {
    const response = await authedFetch("/api/users/rewards").catch(() => null);
    if (!response?.ok) return;
    const payload = (await response.json().catch(() => null)) as Rewards | null;
    if (payload) {
      setRewards(payload);
      setScreenCache<Rewards>("rewards", payload);
    }
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  if (!rewards) return null;
  const earned = rewards.medals.filter((medal) => medal.earned);
  const topMedal = earned[earned.length - 1];

  return (
    <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="rewards-card">
      <View style={styles.row}>
        <View style={[styles.icon, { backgroundColor: palette.soft }]}>
          <Ionicons name="ribbon-outline" size={24} color={palette.brand} />
        </View>
        <View style={styles.copy}>
          <Text style={[styles.points, { color: palette.text }]}>{rewards.points} points</Text>
          <Text style={[styles.subtitle, { color: palette.muted }]}>
            {topMedal ? topMedal.name : rewards.next_medal ? `${rewards.next_medal.threshold - rewards.points} points to ${rewards.next_medal.name}` : "Keep going at your own pace"}
          </Text>
        </View>
        <View style={styles.streak}>
          <Ionicons name="flame-outline" size={19} color={colors.warning} />
          <Text style={[styles.streakText, { color: palette.text }]}>{rewards.streak.current_days}</Text>
        </View>
      </View>
      {rewards.next_medal && !topMedal ? (
        <View style={[styles.track, { backgroundColor: palette.soft }]}>
          <View style={[styles.fill, { width: `${Math.round(rewards.next_medal.progress * 100)}%` }]} />
        </View>
      ) : null}
      <Text style={[styles.message, { color: palette.muted }]}>{rewards.message}</Text>
      {rewards.streak.frozen_days_used > 0 ? (
        <Text style={[styles.freeze, { color: palette.muted }]}>
          <Ionicons name="snow-outline" size={12} color={palette.brand} /> {rewards.streak.freezes_explained}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm, marginBottom: spacing.md },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  icon: { width: 46, height: 46, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  copy: { flex: 1 },
  points: { fontSize: 18, fontWeight: "900" },
  subtitle: { fontSize: 13, lineHeight: 18, marginTop: 2 },
  streak: { flexDirection: "row", alignItems: "center", gap: 4, minWidth: 44, justifyContent: "flex-end" },
  streakText: { fontSize: 17, fontWeight: "900" },
  track: { height: 8, borderRadius: 4, overflow: "hidden" },
  fill: { height: "100%", backgroundColor: colors.success, borderRadius: 4 },
  message: { fontSize: 13, lineHeight: 19 },
  freeze: { fontSize: 12, lineHeight: 17 },
});
