import { Assessment, fetchHistory } from "@/src/api";
import { DEMO_ASSESSMENT_ID } from "@/src/demoAssessment";
import { loadUserPreferences } from "@/src/userPreferences";
import { authedFetch } from "@/src/auth";

export const ALIRA_NAVIGATION_DESTINATIONS = {
  home: { label: "Home", path: "/" },
  journey: { label: "Journey", path: "/(tabs)/journey" },
  progress: { label: "Progress", path: "/progress" },
  assessment_history: { label: "assessment history", path: "/(tabs)/journey" },
  alira_chat: { label: "Alira chat", path: "/(tabs)/chat" },
  journal_entry: { label: "a new journal entry", path: "/(tabs)/journey?action=new-journal" },
  pain_check_in: {
    label: "pain check-in",
    path: "/(tabs)/chat?prompt=Please%20guide%20me%20through%20a%20gentle%20pain%20check-in.%20Ask%20one%20short%20question%20at%20a%20time.",
  },
  daily_reflection: {
    label: "today's reflection",
    path: "/(tabs)/chat?prompt=Please%20guide%20me%20through%20a%20short%20reflection%20on%20today's%20recovery.%20Ask%20one%20encouraging%20question%20at%20a%20time.",
  },
  initial_assessment: {
    label: "initial assessment setup",
    path: "/session-check?target=assessment&mode=initial",
  },
  next_assessment: {
    label: "next assessment setup",
    dynamic: "next-assessment",
  },
  profile: { label: "profile", path: "/(tabs)/profile" },
  care_facility: { label: "care facility profile", path: "/(tabs)/profile" },
  settings: { label: "Settings", path: "/(tabs)/settings" },
  survey_questions: { label: "survey questions", path: "/survey-questions" },
  privacy_policy: { label: "privacy policy", path: "/privacy-policy" },
  data_permissions: { label: "data and permissions", path: "/data-permissions" },
  terms_of_use: { label: "terms of use", path: "/terms-of-use" },
  personal_details: { label: "personal details", path: "/account-center?section=personal" },
  care_circle: { label: "care circle", path: "/account-center?section=care-circle" },
  account_security: { label: "account and password", path: "/account-center?section=account" },
  camera_permissions: { label: "camera and microphone permissions", path: "/account-center?section=permissions" },
  help_center: { label: "Help centre", path: "/account-center?section=help" },
  contact_support: { label: "contact support", path: "/account-center?section=support" },
  function_summary: { label: "function summary", dynamic: "latest-assessment" },
  movement_snapshot: { label: "movement snapshot", dynamic: "latest-assessment" },
  movement_map: { label: "movement map", dynamic: "latest-assessment" },
  rehab_plan: { label: "rehab plan", dynamic: "latest-plan" },
  caregiver_plan: { label: "caregiver exercise programme", path: "/caregiver-plan" },
  survey_report: { label: "assessment report", path: "/survey-report" },
  guided_exercise: { label: "guided exercise", dynamic: "latest-plan" },
  emergency_fast_check: { label: "Emergency FAST check", path: "/(tabs)/emergency" },
  back: { label: "the previous page", action: "back" },
} as const;

export type AliraNavigationDestination = keyof typeof ALIRA_NAVIGATION_DESTINATIONS;

export type AliraNavigationResolution = {
  success: boolean;
  destination: string;
  label: string;
  path?: string;
  action?: "back";
  message: string;
};

function newestFirst(history: Assessment[]) {
  return [...history].sort((left, right) => {
    const leftTime = Date.parse(left.created_at || "") || 0;
    const rightTime = Date.parse(right.created_at || "") || 0;
    return rightTime - leftTime;
  });
}

function latestAssessmentPath(destination: AliraNavigationDestination, id: string) {
  const encodedId = encodeURIComponent(id);
  if (destination === "function_summary") return `/function-summary?id=${encodedId}`;
  if (destination === "movement_map") return `/movement-map?id=${encodedId}`;
  return `/results?id=${encodedId}`;
}

export function isAliraNavigationDestination(value: string): value is AliraNavigationDestination {
  return Object.prototype.hasOwnProperty.call(ALIRA_NAVIGATION_DESTINATIONS, value);
}

export async function resolveAliraNavigation(rawDestination: string): Promise<AliraNavigationResolution> {
  const destination = rawDestination.trim().toLowerCase();
  if (!isAliraNavigationDestination(destination)) {
    return {
      success: false,
      destination,
      label: "that page",
      message: "That destination is not available. Ask the patient which Rehyn page they want to open.",
    };
  }

  const target = ALIRA_NAVIGATION_DESTINATIONS[destination];
  if ("path" in target) {
    return {
      success: true,
      destination,
      label: target.label,
      path: target.path,
      message: `Opening ${target.label}.`,
    };
  }
  if ("action" in target) {
    return {
      success: true,
      destination,
      label: target.label,
      action: target.action,
      message: "Going back to the previous page.",
    };
  }

  if (target.dynamic === "next-assessment") {
    try {
      const response = await authedFetch("/api/alira/care-plan");
      if (response.ok) {
        const carePlan = await response.json();
        if (!carePlan?.assessment?.due || !carePlan?.assessment?.can_start) {
          const dueAt = String(carePlan?.assessment?.due_at || "").slice(0, 10);
          return {
            success: false,
            destination,
            label: target.label,
            message: dueAt
              ? `The next routine assessment is scheduled for ${dueAt}. Ask about a new movement problem if something genuinely changed.`
              : "The next assessment is not due yet. Ask about a new movement problem if something genuinely changed.",
          };
        }
        const packageId = String(
          carePlan?.assessment?.packages?.[0]
          || "",
        );
        const approvedPackages = new Set(["initial", "upper_limb", "hand", "lower_limb", "balance"]);
        if (!approvedPackages.has(packageId)) {
          return {
            success: false,
            destination,
            label: target.label,
            message: "Alira could not select a safe assessment package right now.",
          };
        }
        const taskIds = Array.isArray(carePlan?.assessment?.task_ids)
          ? carePlan.assessment.task_ids.map(String).filter(Boolean)
          : [];
        const query = new URLSearchParams({
          target: "assessment",
          mode: packageId === "initial" ? "initial" : "followup",
          package: packageId,
        });
        if (taskIds.length) query.set("task_ids", taskIds.join(","));
        return {
          success: true,
          destination,
          label: target.label,
          path: `/session-check?${query.toString()}`,
          message: `Opening ${target.label}.`,
        };
      }
    } catch {
      // Assessment access stays closed when the current schedule cannot be verified.
    }
    return {
      success: false,
      destination,
      label: target.label,
      message: "I could not verify whether an assessment is due. Please try again when Rehyn is connected.",
    };
  }

  const [history, preferences] = await Promise.all([
    fetchHistory().catch(() => []),
    loadUserPreferences(),
  ]);
  const assessments = newestFirst(history);

  if (target.dynamic === "latest-plan") {
    const latestPlan = assessments.find(
      (assessment) => assessment.rehab_plan.length > 0
        && (assessment.clinical_review_gate?.rehab_access ?? "allowed") === "allowed",
    );
    const id = latestPlan?.id || (preferences.demoMode ? DEMO_ASSESSMENT_ID : "");
    if (!id) {
      return {
        success: false,
        destination,
        label: target.label,
        message: "A rehab plan is not available yet. Offer to open the assessment or Journey page instead.",
      };
    }
    return {
      success: true,
      destination,
      label: target.label,
      path: `/rehab-plan?id=${encodeURIComponent(id)}`,
      message: `Opening ${target.label}.`,
    };
  }

  const id = assessments[0]?.id || (preferences.demoMode ? DEMO_ASSESSMENT_ID : "");
  if (!id) {
    return {
      success: false,
      destination,
      label: target.label,
      message: "There is no completed assessment to open yet. Offer to open the initial assessment or Journey page instead.",
    };
  }
  return {
    success: true,
    destination,
    label: target.label,
    path: latestAssessmentPath(destination, id),
    message: `Opening ${target.label}.`,
  };
}
