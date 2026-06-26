import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, radius, spacing } from "@/src/theme";
import { fetchBalance } from "@/src/auth";

export default function CreditsBadge() {
  const [credits, setCredits] = useState<number | null>(null);
  const router = useRouter();

  const load = async () => {
    try {
      const b = await fetchBalance();
      setCredits(b.credits);
    } catch { setCredits(null); }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 6000); // refresh every 6s
    return () => clearInterval(t);
  }, []);

  return (
    <Pressable onPress={() => router.push("/credits")} style={styles.wrap} testID="credits-badge">
      <Ionicons name="diamond" size={14} color={colors.brandSecondary} />
      <Text style={styles.text}>{credits == null ? "—" : credits}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandTertiary, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, alignSelf: "flex-start" },
  text: { color: colors.onBrandTertiary, fontWeight: "800", fontSize: 13 },
});
