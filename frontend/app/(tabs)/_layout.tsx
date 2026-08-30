import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Platform, Text, View } from "react-native";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { colors } from "@/src/theme";

export default function TabsLayout() {
  const isWeb = Platform.OS === "web";
  const { palette, scale } = useDisplayPreferences();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: palette.brand,
        tabBarInactiveTintColor: palette.muted,
        tabBarStyle: {
          backgroundColor: palette.surface,
          borderTopColor: palette.border,
          height: isWeb ? 80 : Platform.OS === "ios" ? 88 : 64,
          paddingBottom: isWeb ? 14 : Platform.OS === "ios" ? 28 : 8,
          paddingTop: isWeb ? 7 : 8,
        },
        tabBarItemStyle: { minHeight: 58 },
        tabBarLabelStyle: {
          fontSize: 11 * scale,
          lineHeight: 16 * scale,
          fontWeight: "600",
          marginBottom: isWeb ? 2 : 0,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          tabBarIcon: ({ color, size }) => <Ionicons name="home" size={size} color={color} />,
          tabBarButtonTestID: "tab-home",
        }}
      />
      <Tabs.Screen
        name="journey"
        options={{
          title: "Journey",
          tabBarIcon: ({ color, size }) => <Ionicons name="book-outline" size={size} color={color} />,
          tabBarButtonTestID: "tab-journey",
        }}
      />
      <Tabs.Screen
        name="chat"
        options={{
          title: "Alira",
          tabBarIcon: ({ color, size }) => <Ionicons name="chatbubbles" size={size} color={color} />,
          tabBarButtonTestID: "tab-chat",
        }}
      />
      <Tabs.Screen
        name="emergency"
        options={{
          title: "Emergency",
          tabBarLabel: () => <Text style={{ color: colors.error, fontSize: 11 * scale, lineHeight: 16 * scale, fontWeight: "800" }}>Emergency</Text>,
          tabBarIcon: () => (
            <View style={{ width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center", backgroundColor: "#FCE6E3" }}>
              <Ionicons name="warning" size={21} color={colors.error} />
            </View>
          ),
          tabBarButtonTestID: "tab-emergency-fast",
        }}
      />
      <Tabs.Screen
        name="community"
        options={{ href: null }}
      />
      <Tabs.Screen
        name="therapists"
        options={{ href: null }}
      />
      <Tabs.Screen
        name="profile"
        options={{ href: null }}
      />
      <Tabs.Screen
        name="settings"
        options={{ href: null }}
      />
    </Tabs>
  );
}
