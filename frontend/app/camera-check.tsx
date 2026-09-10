import { Redirect, useLocalSearchParams } from "expo-router";

// Preserve old bookmarks; the assessment owns its fresh setup gate.
export default function CameraCheckScreen() {
  const params = useLocalSearchParams<Record<string, string>>();
  return <Redirect href={{ pathname: "/assessment", params }} />;
}
