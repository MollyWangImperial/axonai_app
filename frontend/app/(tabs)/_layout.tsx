import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Platform } from "react-native";
import { useDisplayPreferences } from "@/src/displayPreferences";

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
      {/* The Emergency FAST check stays reachable from the prominent red
          banner on Home; it is hidden from the tab bar so the bar keeps
          three tabs: Home, Journey, Alira. */}
      <Tabs.Screen
        name="emergency"
        options={{ href: null }}
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
