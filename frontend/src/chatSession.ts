// The Alira text-chat session id, shared by the chat tab and the places that
// post into the conversation on Alira's behalf (the daily exercise reminder).
import { storage } from "@/src/utils/storage";

export const CHAT_SESSION_KEY = "alira_session_id";

function generateChatSessionId() {
  return "s_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

export async function getOrCreateChatSessionId(): Promise<string> {
  const stored = await storage.getItem<string>(CHAT_SESSION_KEY, "");
  if (stored) return stored;
  const id = generateChatSessionId();
  await storage.setItem(CHAT_SESSION_KEY, id);
  return id;
}
