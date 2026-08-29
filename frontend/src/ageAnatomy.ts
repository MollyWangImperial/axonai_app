import type { ImageSourcePropType } from "react-native";

import { authedFetch, getCachedPatientProfile, getUserId } from "@/src/auth";

export type AgeAnatomyPresentation = {
  source: ImageSourcePropType;
  surveyLabel: string | null;
  viewLabel: string;
  shoulderX: number;
  shoulderY: number;
  handX: number;
  handY: number;
  lowerLimbX: number;
  lowerLimbY: number;
};

const youthAnatomy = require("@/assets/images/rehyn-anatomy-youth-front.png");
const adultAnatomy = require("@/assets/images/rehyn-anatomy-adult-front.png");
const midlifeAnatomy = require("@/assets/images/rehyn-anatomy-midlife-front.png");
const olderAnatomy = require("@/assets/images/rehyn-anatomy-older-front.png");
const standardAnatomy = require("@/assets/images/rehyn-anatomy-front.png");

const AGE_BAND_LABELS: Record<string, string> = {
  under_20: "Under 20",
  "20-29": "20–29",
  "30-39": "30–39",
  "40-49": "40–49",
  "50-59": "50–59",
  "60-69": "60–69",
  "70-79": "70–79",
  "80+": "80 or older",
};

export function getAgeAnatomyPresentation(ageBand: string | null): AgeAnatomyPresentation {
  const surveyLabel = ageBand ? AGE_BAND_LABELS[ageBand] || null : null;
  if (ageBand === "under_20") {
    return { source: youthAnatomy, surveyLabel, viewLabel: "Youth anatomy view", shoulderX: 29.5, shoulderY: 20.5, handX: 13, handY: 49, lowerLimbX: 42, lowerLimbY: 70 };
  }
  if (["20-29", "30-39", "40-49"].includes(ageBand || "")) {
    return { source: adultAnatomy, surveyLabel, viewLabel: "Adult anatomy view", shoulderX: 29.5, shoulderY: 20.5, handX: 13, handY: 48, lowerLimbX: 42, lowerLimbY: 70 };
  }
  if (["50-59", "60-69"].includes(ageBand || "")) {
    return { source: midlifeAnatomy, surveyLabel, viewLabel: "Midlife anatomy view", shoulderX: 30, shoulderY: 20.5, handX: 13, handY: 49, lowerLimbX: 42, lowerLimbY: 70 };
  }
  if (["70-79", "80+"].includes(ageBand || "")) {
    return { source: olderAnatomy, surveyLabel, viewLabel: "Older adult anatomy view", shoulderX: 29.5, shoulderY: 21.5, handX: 13, handY: 49, lowerLimbX: 42, lowerLimbY: 70 };
  }
  return { source: standardAnatomy, surveyLabel: null, viewLabel: "Standard anatomy view", shoulderX: 25, shoulderY: 24.5, handX: 20, handY: 50, lowerLimbX: 42, lowerLimbY: 70 };
}

export async function loadPatientAgeBand(): Promise<string | null> {
  const userId = await getUserId();
  const cached = userId ? await getCachedPatientProfile(userId) : null;
  const cachedAgeBand = typeof cached?.age_band === "string" ? cached.age_band : null;

  try {
    const response = await authedFetch("/api/users/onboarding");
    if (!response.ok) return cachedAgeBand;
    const onboarding = await response.json();
    return typeof onboarding?.profile?.age_band === "string" ? onboarding.profile.age_band : cachedAgeBand;
  } catch {
    return cachedAgeBand;
  }
}
