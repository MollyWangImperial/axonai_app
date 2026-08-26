"""Clinical task definitions beyond the original upper-limb package.

These tasks are video-based functional screens. They do not replace manual
muscle testing, tone examination, force plates, pressure insoles, or a
therapist's safety assessment.
"""

from typing import Any, Dict, List


def _phenotype(
    code: str,
    domain: str,
    label: str,
    description: str,
    severity: str,
    source: str,
    rehab_code: str,
) -> Dict[str, str]:
    return {
        "code": code,
        "domain": domain,
        "label": label,
        "description": description,
        "severity": severity,
        "source": source,
        "rehab_code": rehab_code,
    }


HAND_STEP_PHENOTYPES: Dict[str, Dict[str, str]] = {
    "H1-S1": _phenotype("HAND_POSITIONING_IMPAIRED", "hand_task_positioning", "Difficulty positioning the hand", "The affected hand did not reach a visible chest-height working position.", "moderate", "Task-specific observation; Fugl-Meyer UE", "HAND_OPENING"),
    "H1-S2": _phenotype("HAND_OPENING", "active_hand_opening", "Difficulty opening the hand", "Finger extension and palm opening were insufficient for the requested open-hand posture.", "moderate", "Fugl-Meyer UE hand section", "HAND_OPENING"),
    "H1-S3": _phenotype("HAND_RETURN_IMPAIRED", "hand_return_control", "Difficulty lowering the hand to rest", "The affected hand did not complete a controlled return to the lap.", "mild", "Task-specific movement observation", "HAND_OPENING"),
    "H2-S1": _phenotype("FIST_PREPARATION_IMPAIRED", "fist_preparation", "Difficulty preparing the hand for closure", "The affected hand could not be positioned for the fist task.", "moderate", "Task-specific observation; Fugl-Meyer UE", "GROSS_GRASP"),
    "H2-S2": _phenotype("FIST_CLOSURE_IMPAIRED", "mass_finger_flexion", "Incomplete fist closure", "The fingers did not complete the requested mass-flexion pattern.", "moderate", "Fugl-Meyer UE hand section", "GROSS_GRASP"),
    "H2-S3": _phenotype("HAND_RELAXATION_IMPAIRED", "hand_relaxation", "Difficulty relaxing after fist closure", "The hand did not reopen or return toward a relaxed position after closure.", "moderate", "Task-specific movement observation", "HAND_OPENING"),
    "H3-S1": _phenotype("PINCH_POSITIONING_IMPAIRED", "pinch_task_positioning", "Difficulty positioning the hand for pinch", "The affected hand did not reach the working position for pinch.", "moderate", "Task-specific movement observation", "PINCH_IMPAIRED"),
    "H3-S2": _phenotype("PINCH_IMPAIRED", "thumb_index_opposition", "Difficulty forming thumb-index pinch", "Thumb-index opposition did not reach the requested pinch configuration.", "moderate", "ARAT pinch subscale; Fugl-Meyer UE hand section", "PINCH_IMPAIRED"),
    "H3-S3": _phenotype("PINCH_RELEASE_IMPAIRED", "pinch_release", "Difficulty releasing pinch", "The thumb and index finger did not separate after the pinch.", "mild", "Task-specific movement observation", "PINCH_IMPAIRED"),
    "H4-S1": _phenotype("HAND_OPENING", "active_hand_opening", "Difficulty opening the hand", "The hand did not reach the requested open posture.", "moderate", "Fugl-Meyer UE hand section", "HAND_OPENING"),
    "H4-S2": _phenotype("HAND_CYCLING_IMPAIRED", "hand_open_close_control", "Impaired repeated hand opening and closing", "The hand did not complete a controlled close-open cycle.", "moderate", "Task-specific movement observation", "HAND_OPENING"),
    "H4-S3": _phenotype("HAND_RETURN_IMPAIRED", "hand_return_control", "Difficulty lowering the hand to rest", "The affected hand did not return to the resting position.", "mild", "Task-specific movement observation", "HAND_OPENING"),
    "H5-S1": _phenotype("OBJECT_REACH_IMPAIRED", "object_directed_reach", "Difficulty reaching to an object", "The affected hand did not reach the marked object.", "moderate", "ARAT grasp subscale", "GROSS_GRASP"),
    "H5-S2": _phenotype("GROSS_GRASP", "gross_grasp_acquisition", "Difficulty grasping and holding an object", "The hand did not establish and maintain coupling with the marked object.", "moderate", "ARAT grasp subscale", "GROSS_GRASP"),
    "H5-S3": _phenotype("OBJECT_PLACEMENT_IMPAIRED", "object_placement", "Difficulty placing an object", "The object was not returned to the requested placement area.", "mild", "ARAT; task-specific movement observation", "GROSS_GRASP"),
    "H6-S1": _phenotype("GRASP_HOLD_UNSTABLE", "grasp_hold_stability", "Unstable object hold", "The affected hand could not maintain a stable grasp on the object.", "moderate", "ARAT grasp subscale", "GROSS_GRASP"),
    "H6-S2": _phenotype("OBJECT_RELEASE_IMPAIRED", "object_release", "Difficulty releasing an object", "The object reached the target but release was delayed or incomplete.", "moderate", "ARAT grasp subscale", "GROSS_GRASP"),
    "H6-S3": _phenotype("HAND_OBJECT_SEPARATION_IMPAIRED", "post_release_separation", "Difficulty moving the hand away after release", "The hand remained coupled to the object after the requested release.", "mild", "Task-specific movement observation", "GROSS_GRASP"),
    "H7-S1": _phenotype("WRIST_POSITIONING_IMPAIRED", "wrist_task_positioning", "Difficulty positioning the wrist", "The forearm and hand were not positioned for wrist control assessment.", "moderate", "Fugl-Meyer UE wrist section", "HAND_OPENING"),
    "H7-S2": _phenotype("WRIST_EXTENSION_CONTROL_IMPAIRED", "wrist_extension_control", "Impaired wrist lift and stabilization", "The wrist did not lift and remain stable with relaxed fingers.", "moderate", "Fugl-Meyer UE wrist section", "HAND_OPENING"),
    "H7-S3": _phenotype("WRIST_RETURN_IMPAIRED", "wrist_return_control", "Difficulty relaxing the wrist", "The wrist did not complete a controlled return to rest.", "mild", "Task-specific movement observation", "HAND_OPENING"),
}


LOWER_LIMB_TASKS_DATA: List[Dict[str, Any]] = [
    {
        "id": "L1",
        "title": "Seated Knee Extension",
        "view": "Side view",
        "focus": "Antigravity knee extension, selective control, return control",
        "safety_tier": "seated",
        "safety_note": "Use a stable chair with the patient's back supported.",
        "steps": [
            {"id": "L1-S1", "voice": "Sit well back in a stable chair with both feet on the floor. Keep your trunk upright.", "target": {"x": 0.5, "y": 0.80, "r": 0.14, "landmark": "SEATED_READY"}, "hold_ms": 1200, "movement_required": False, "caption": "Sit upright with feet supported", "failure_phenotype": _phenotype("SEATED_LOWER_LIMB_SETUP_IMPAIRED", "seated_lower_limb_setup", "Difficulty maintaining the seated test position", "The patient did not maintain an upright supported sitting position with the feet placed for testing.", "moderate", "Fugl-Meyer LE; task-specific observation", "LOWER_LIMB_SELECTIVE_CONTROL")},
            {"id": "L1-S2", "voice": "Slowly straighten the affected knee as far as you comfortably can. Keep your thigh on the chair.", "target": {"x": 0.58, "y": 0.67, "r": 0.14, "landmark": "KNEE_EXTENDED"}, "hold_ms": 1300, "caption": "Straighten the affected knee", "measure": ["knee_extension_rom", "trunk_compensation"], "failure_phenotype": _phenotype("KNEE_EXTENSION_CONTROL_IMPAIRED", "active_knee_extension", "Limited active knee extension", "The affected knee did not reach the requested antigravity extension range.", "moderate", "Fugl-Meyer LE; task-specific movement observation", "LOWER_LIMB_SELECTIVE_CONTROL")},
            {"id": "L1-S3", "voice": "Hold the lower leg steady for a moment.", "target": {"x": 0.58, "y": 0.67, "r": 0.14, "landmark": "KNEE_EXTENDED_STABLE"}, "hold_ms": 1500, "movement_required": False, "caption": "Hold the knee extended", "failure_phenotype": _phenotype("KNEE_EXTENSION_HOLD_UNSTABLE", "knee_extension_hold", "Unstable knee extension hold", "The extended lower leg could not be maintained steadily.", "mild", "Task-specific movement observation", "LOWER_LIMB_SELECTIVE_CONTROL")},
            {"id": "L1-S4", "voice": "Slowly lower the foot back to the floor.", "target": {"x": 0.5, "y": 0.82, "r": 0.15, "landmark": "FOOT_RETURNED"}, "hold_ms": 1200, "caption": "Return the foot to the floor", "failure_phenotype": _phenotype("KNEE_RETURN_CONTROL_IMPAIRED", "knee_extension_return", "Difficulty controlling knee return", "The foot did not return to the floor with controlled knee flexion.", "mild", "Task-specific movement observation", "LOWER_LIMB_SELECTIVE_CONTROL")},
        ],
    },
    {
        "id": "L2",
        "title": "Seated Ankle Dorsiflexion",
        "view": "Side or front view",
        "focus": "Toe clearance potential and selective ankle control",
        "safety_tier": "seated",
        "safety_note": "Keep the heel on the floor and the chair stable.",
        "steps": [
            {"id": "L2-S1", "voice": "Keep the affected heel on the floor and relax the toes.", "target": {"x": 0.5, "y": 0.84, "r": 0.15, "landmark": "FOOT_RETURNED"}, "hold_ms": 1000, "movement_required": False, "caption": "Heel down, foot relaxed", "failure_phenotype": _phenotype("ANKLE_SETUP_IMPAIRED", "ankle_task_setup", "Difficulty positioning the foot", "The affected foot could not be positioned for ankle dorsiflexion screening.", "moderate", "Fugl-Meyer LE", "ANKLE_DORSIFLEXION_CONTROL")},
            {"id": "L2-S2", "voice": "Lift the front of the affected foot and toes while keeping the heel down.", "target": {"x": 0.5, "y": 0.78, "r": 0.14, "landmark": "TOES_LIFTED"}, "hold_ms": 1300, "caption": "Lift toes with heel down", "measure": ["ankle_dorsiflexion_proxy", "toe_clearance_proxy"], "failure_phenotype": _phenotype("ANKLE_DORSIFLEXION_CONTROL_IMPAIRED", "active_ankle_dorsiflexion", "Limited ankle dorsiflexion control", "The forefoot did not lift while the heel remained supported.", "moderate", "Fugl-Meyer LE; observational gait analysis", "ANKLE_DORSIFLEXION_CONTROL")},
            {"id": "L2-S3", "voice": "Lower the toes slowly back to the floor.", "target": {"x": 0.5, "y": 0.84, "r": 0.15, "landmark": "FOOT_RETURNED"}, "hold_ms": 1000, "caption": "Lower toes under control", "failure_phenotype": _phenotype("ANKLE_RETURN_CONTROL_IMPAIRED", "ankle_return_control", "Difficulty controlling ankle return", "The forefoot did not return smoothly to the supported position.", "mild", "Task-specific movement observation", "ANKLE_DORSIFLEXION_CONTROL")},
        ],
    },
    {
        "id": "L3",
        "title": "Supported Sit to Stand",
        "view": "Side view",
        "focus": "Transfer ability, lower-limb support, symmetry, trunk strategy",
        "safety_tier": "spotter_required",
        "safety_note": "Only attempt with a therapist or capable caregiver beside the patient and a stable support in front.",
        "steps": [
            {"id": "L3-S1", "voice": "Place both feet under your knees. Move toward the front of the chair and keep your support within reach.", "target": {"x": 0.5, "y": 0.76, "r": 0.14, "landmark": "SIT_TO_STAND_READY"}, "hold_ms": 1200, "movement_required": False, "caption": "Prepare feet and trunk for standing", "failure_phenotype": _phenotype("SIT_TO_STAND_SETUP_IMPAIRED", "sit_to_stand_setup", "Difficulty preparing for sit to stand", "Foot placement and forward preparation were insufficient for a safe transfer attempt.", "moderate", "Five Times Sit-to-Stand task analysis", "SIT_TO_STAND_IMPAIRED")},
            {"id": "L3-S2", "voice": "Lean your trunk forward, push through both feet, and stand using the support as needed.", "target": {"x": 0.5, "y": 0.52, "r": 0.16, "landmark": "HIP_RISEN"}, "hold_ms": 1400, "caption": "Rise from the chair", "measure": ["sit_to_stand_time", "trunk_lean", "weight_shift_symmetry"], "failure_phenotype": _phenotype("SIT_TO_STAND_IMPAIRED", "sit_to_stand_transfer", "Difficulty rising from a chair", "The patient did not complete the seat-off and rising phase of the transfer.", "severe", "Five Times Sit-to-Stand; task-specific mobility assessment", "SIT_TO_STAND_IMPAIRED")},
            {"id": "L3-S3", "voice": "Stand tall with the support and keep both knees steady.", "target": {"x": 0.5, "y": 0.46, "r": 0.16, "landmark": "STAND_UPRIGHT"}, "hold_ms": 1500, "movement_required": False, "caption": "Stabilize in supported standing", "failure_phenotype": _phenotype("SUPPORTED_STANDING_UNSTABLE", "supported_standing_control", "Unstable supported standing", "The patient rose but could not maintain aligned supported standing.", "severe", "PASS; Berg Balance Scale task concepts", "SUPPORTED_STANDING_CONTROL")},
            {"id": "L3-S4", "voice": "Reach back for the chair and sit down slowly with control.", "target": {"x": 0.5, "y": 0.77, "r": 0.15, "landmark": "HIP_SEATED"}, "hold_ms": 1400, "caption": "Sit down slowly", "failure_phenotype": _phenotype("STAND_TO_SIT_CONTROL_IMPAIRED", "stand_to_sit_transfer", "Difficulty controlling stand to sit", "The lowering phase back to the chair was not completed with control.", "moderate", "Task-specific mobility assessment", "SIT_TO_STAND_IMPAIRED")},
        ],
    },
    {
        "id": "L4",
        "title": "Supported Step Forward and Return",
        "view": "Side or 45-degree view",
        "focus": "Step initiation, foot clearance, placement and return control",
        "safety_tier": "spotter_required",
        "safety_note": "Use a fixed support and close guarding. Skip if supported standing is not safe.",
        "steps": [
            {"id": "L4-S1", "voice": "Stand with your support and settle your weight evenly before stepping.", "target": {"x": 0.5, "y": 0.82, "r": 0.15, "landmark": "SUPPORTED_STAND_STABLE"}, "hold_ms": 1500, "movement_required": False, "caption": "Settle in supported standing", "failure_phenotype": _phenotype("STEP_TASK_SETUP_UNSAFE", "step_task_setup", "Unable to establish a safe step position", "Stable supported standing was not established before step initiation.", "severe", "PASS; observational gait analysis", "SUPPORTED_STANDING_CONTROL")},
            {"id": "L4-S2", "voice": "Move weight onto the stronger leg and step the affected foot forward a short distance.", "target": {"x": 0.56, "y": 0.78, "r": 0.16, "landmark": "AFFECTED_FOOT_FORWARD"}, "hold_ms": 1200, "caption": "Step the affected foot forward", "measure": ["step_length_ratio", "toe_clearance_proxy", "circumduction_proxy"], "failure_phenotype": _phenotype("AFFECTED_STEP_INITIATION_IMPAIRED", "affected_step_initiation", "Difficulty initiating an affected-side step", "The affected foot did not clear and advance to the forward step position.", "severe", "Observational gait analysis; Fugl-Meyer LE", "GAIT_INITIATION_IMPAIRED")},
            {"id": "L4-S3", "voice": "Bring the affected foot back beside the other foot with control.", "target": {"x": 0.5, "y": 0.82, "r": 0.15, "landmark": "AFFECTED_FOOT_RETURNED"}, "hold_ms": 1200, "caption": "Return the affected foot", "failure_phenotype": _phenotype("STEP_RETURN_CONTROL_IMPAIRED", "step_return_control", "Difficulty returning the affected foot", "The affected foot did not return to the starting stance with control.", "moderate", "Task-specific gait observation", "GAIT_INITIATION_IMPAIRED")},
        ],
    },
    {
        "id": "L5",
        "title": "Supported Alternating March",
        "view": "Front view",
        "focus": "Single-limb support tolerance, hip-knee flexion and rhythm",
        "safety_tier": "spotter_required",
        "safety_note": "Use a fixed support and close guarding. This is not an independent gait clearance test.",
        "steps": [
            {"id": "L5-S1", "voice": "Stand with support, feet apart, and pause until you feel steady.", "target": {"x": 0.5, "y": 0.82, "r": 0.16, "landmark": "SUPPORTED_STAND_STABLE"}, "hold_ms": 1500, "movement_required": False, "caption": "Settle before marching", "failure_phenotype": _phenotype("MARCH_SETUP_UNSAFE", "march_setup", "Unable to establish a safe marching position", "Stable supported standing was not established for marching.", "severe", "PASS; task-specific mobility assessment", "SUPPORTED_STANDING_CONTROL")},
            {"id": "L5-S2", "voice": "Lift the affected knee, then place the foot down slowly.", "target": {"x": 0.5, "y": 0.68, "r": 0.16, "landmark": "AFFECTED_KNEE_LIFTED"}, "hold_ms": 1000, "caption": "Lift the affected knee", "measure": ["hip_knee_flexion", "pelvic_hike", "trunk_compensation"], "failure_phenotype": _phenotype("AFFECTED_SWING_CLEARANCE_IMPAIRED", "affected_swing_clearance", "Reduced affected-side swing clearance", "The affected hip and knee did not produce sufficient foot clearance for the marching step.", "severe", "Observational gait analysis; Fugl-Meyer LE", "GAIT_INITIATION_IMPAIRED")},
            {"id": "L5-S3", "voice": "Lift the other knee, then place the foot down. Keep your trunk centered.", "target": {"x": 0.5, "y": 0.68, "r": 0.16, "landmark": "UNAFFECTED_KNEE_LIFTED"}, "hold_ms": 1000, "caption": "Lift the other knee", "measure": ["affected_stance_tolerance", "lateral_trunk_shift"], "failure_phenotype": _phenotype("AFFECTED_STANCE_TOLERANCE_IMPAIRED", "affected_stance_tolerance", "Reduced support on the affected leg", "The patient could not maintain affected-limb support while lifting the other knee.", "severe", "Observational gait analysis", "WEIGHT_BEARING_ASYMMETRY")},
        ],
    },
    {
        "id": "L6",
        "title": "Comfortable Walk",
        "view": "Side view",
        "focus": "Gait initiation, step progression, foot clearance, trunk control",
        "safety_tier": "spotter_required",
        "safety_note": "Only attempt this task if walking is already part of your usual routine. Use your normal walking aid and have another person nearby if you normally need support.",
        "steps": [
            {
                "id": "L6-S1",
                "voice": "For the walking task, place the phone where your whole body is visible from the side. Use your usual walking aid. Only continue if walking is normally safe for you, and have someone nearby if you usually need help. Stand near one side of the camera view when you are ready.",
                "target": {"x": 0.22, "y": 0.78, "r": 0.16, "landmark": "WALK_READY"},
                "hold_ms": 1500,
                "movement_required": False,
                "caption": "Stand safely at one side of the camera view",
                "failure_phenotype": _phenotype("GAIT_SETUP_UNSAFE", "gait_setup", "Unable to establish a safe walking start", "A safe, fully visible standing position was not established before the walking observation.", "severe", "Observational gait analysis; task-specific safety screening", "SUPPORTED_STANDING_CONTROL"),
            },
            {
                "id": "L6-S2",
                "voice": "Now walk at your usual comfortable pace across the camera view. Take several natural steps. Do not walk faster or farther than feels safe.",
                "target": {"x": 0.78, "y": 0.78, "r": 0.17, "landmark": "WALK_ACROSS"},
                "hold_ms": 900,
                "caption": "Walk several comfortable steps across the view",
                "measure": ["gait_progression", "step_count_proxy", "toe_clearance_proxy", "circumduction_proxy", "trunk_compensation"],
                "failure_phenotype": _phenotype("GAIT_PROGRESSION_IMPAIRED", "gait_progression", "Difficulty progressing during walking", "The patient did not complete several observable steps across the camera view at a comfortable pace.", "severe", "Observational gait analysis", "GAIT_INITIATION_IMPAIRED"),
            },
            {
                "id": "L6-S3",
                "voice": "Stop in a safe position and stand still with your usual support for a moment.",
                "target": {"x": 0.78, "y": 0.78, "r": 0.17, "landmark": "WALK_STOPPED"},
                "hold_ms": 1500,
                "movement_required": False,
                "caption": "Stop safely and stand steady",
                "failure_phenotype": _phenotype("GAIT_STOP_CONTROL_IMPAIRED", "gait_termination", "Difficulty stopping safely after walking", "The patient did not establish a stable supported stop after the walking observation.", "severe", "Observational gait analysis; task-specific safety screening", "SUPPORTED_STANDING_CONTROL"),
            },
        ],
    },
]


BALANCE_TASKS_DATA: List[Dict[str, Any]] = [
    {
        "id": "B1",
        "title": "Unsupported Sitting Hold",
        "view": "Front view",
        "focus": "Static sitting alignment and sway",
        "safety_tier": "seated",
        "safety_note": "Use a stable chair or bed edge with a caregiver nearby.",
        "steps": [
            {"id": "B1-S1", "voice": "Sit with both feet supported and place your hands on your thighs.", "target": {"x": 0.5, "y": 0.54, "r": 0.16, "landmark": "SEATED_READY"}, "hold_ms": 1200, "movement_required": False, "caption": "Set up a stable sitting position", "failure_phenotype": _phenotype("SITTING_SETUP_IMPAIRED", "sitting_setup", "Difficulty establishing sitting balance", "The patient did not establish the requested supported-foot sitting position.", "moderate", "PASS; Berg Balance Scale task concepts", "SITTING_BALANCE_IMPAIRED")},
            {"id": "B1-S2", "voice": "Let go of external support if your therapist says it is safe. Sit still and upright.", "target": {"x": 0.5, "y": 0.52, "r": 0.16, "landmark": "SEATED_STABLE"}, "hold_ms": 3000, "movement_required": False, "caption": "Hold unsupported sitting", "measure": ["trunk_sway", "midline_alignment"], "failure_phenotype": _phenotype("SITTING_BALANCE_IMPAIRED", "static_sitting_balance", "Impaired static sitting balance", "The patient could not maintain upright unsupported sitting for the requested interval.", "severe", "PASS; Berg Balance Scale task concepts", "SITTING_BALANCE_IMPAIRED")},
        ],
    },
    {
        "id": "B2",
        "title": "Seated Lateral Reach",
        "view": "Front view",
        "focus": "Limits of stability, controlled weight shift and return to midline",
        "safety_tier": "seated",
        "safety_note": "Place the chair against a wall and have a caregiver guard the affected side.",
        "steps": [
            {"id": "B2-S1", "voice": "Sit upright in the middle with both feet supported.", "target": {"x": 0.5, "y": 0.52, "r": 0.15, "landmark": "SEATED_STABLE"}, "hold_ms": 1200, "movement_required": False, "caption": "Start at midline", "failure_phenotype": _phenotype("SEATED_REACH_SETUP_IMPAIRED", "seated_reach_setup", "Difficulty preparing for seated reach", "A stable midline sitting position was not established.", "moderate", "PASS; functional reach task concept", "SITTING_BALANCE_IMPAIRED")},
            {"id": "B2-S2", "voice": "Reach the affected arm slightly to the side while keeping both hips on the seat.", "target": {"x": 0.68, "y": 0.52, "r": 0.15, "landmark": "TRUNK_SHIFT_AFFECTED"}, "hold_ms": 1200, "caption": "Shift toward the affected side", "measure": ["seated_lateral_reach", "pelvic_stability"], "failure_phenotype": _phenotype("AFFECTED_SIDE_LIMIT_OF_STABILITY_REDUCED", "seated_affected_limit_of_stability", "Reduced seated stability toward the affected side", "The patient did not complete a controlled affected-side weight shift while keeping the pelvis supported.", "moderate", "PASS; functional reach task concept", "SITTING_BALANCE_IMPAIRED")},
            {"id": "B2-S3", "voice": "Return slowly to the middle and sit upright again.", "target": {"x": 0.5, "y": 0.52, "r": 0.15, "landmark": "SEATED_STABLE"}, "hold_ms": 1200, "caption": "Return to midline", "failure_phenotype": _phenotype("SEATED_MIDLINE_RETURN_IMPAIRED", "seated_midline_return", "Difficulty returning to seated midline", "The patient did not regain the upright midline position after reaching.", "moderate", "PASS; task-specific balance observation", "SITTING_BALANCE_IMPAIRED")},
        ],
    },
    {
        "id": "B3",
        "title": "Supported Standing Hold",
        "view": "Front view",
        "focus": "Static standing stability, alignment and support dependence",
        "safety_tier": "spotter_required",
        "safety_note": "Only attempt with a therapist or capable caregiver and a fixed support.",
        "steps": [
            {"id": "B3-S1", "voice": "Stand using the fixed support and place both feet comfortably apart.", "target": {"x": 0.5, "y": 0.50, "r": 0.16, "landmark": "STAND_UPRIGHT"}, "hold_ms": 1400, "caption": "Rise into supported standing", "failure_phenotype": _phenotype("SUPPORTED_STAND_ENTRY_IMPAIRED", "supported_stand_entry", "Difficulty entering supported standing", "The patient did not reach an aligned supported standing position.", "severe", "PASS; Berg Balance Scale task concepts", "SUPPORTED_STANDING_CONTROL")},
            {"id": "B3-S2", "voice": "Keep both knees steady and hold the supported standing position.", "target": {"x": 0.5, "y": 0.50, "r": 0.16, "landmark": "SUPPORTED_STAND_STABLE"}, "hold_ms": 3000, "movement_required": False, "caption": "Hold supported standing", "measure": ["standing_sway", "weight_shift_symmetry", "knee_stability"], "failure_phenotype": _phenotype("SUPPORTED_STANDING_UNSTABLE", "supported_standing_control", "Unstable supported standing", "The patient could not maintain the supported standing position steadily.", "severe", "PASS; Berg Balance Scale task concepts", "SUPPORTED_STANDING_CONTROL")},
        ],
    },
    {
        "id": "B4",
        "title": "Supported Lateral Weight Shift",
        "view": "Front view",
        "focus": "Affected-side loading tolerance and controlled recentering",
        "safety_tier": "spotter_required",
        "safety_note": "Use a fixed support and close guarding. Do not lift either foot.",
        "steps": [
            {"id": "B4-S1", "voice": "Stand with support and settle your weight in the middle.", "target": {"x": 0.5, "y": 0.52, "r": 0.15, "landmark": "SUPPORTED_STAND_STABLE"}, "hold_ms": 1400, "movement_required": False, "caption": "Start in centered standing", "failure_phenotype": _phenotype("WEIGHT_SHIFT_SETUP_UNSAFE", "weight_shift_setup", "Unable to establish a safe weight-shift position", "Stable supported standing was not established.", "severe", "PASS; task-specific balance assessment", "SUPPORTED_STANDING_CONTROL")},
            {"id": "B4-S2", "voice": "Shift your pelvis slowly toward the affected leg while keeping both feet down.", "target": {"x": 0.60, "y": 0.52, "r": 0.15, "landmark": "WEIGHT_SHIFT_AFFECTED"}, "hold_ms": 1300, "caption": "Shift toward the affected leg", "measure": ["affected_load_proxy", "pelvis_shift", "trunk_compensation"], "failure_phenotype": _phenotype("WEIGHT_BEARING_ASYMMETRY", "affected_weight_acceptance", "Reduced affected-side weight acceptance", "The pelvis did not shift over the affected foot without excessive trunk compensation.", "severe", "PASS; observational balance assessment", "WEIGHT_BEARING_ASYMMETRY")},
            {"id": "B4-S3", "voice": "Return slowly to the middle and hold steady.", "target": {"x": 0.5, "y": 0.52, "r": 0.15, "landmark": "SUPPORTED_STAND_STABLE"}, "hold_ms": 1300, "caption": "Return to centered standing", "failure_phenotype": _phenotype("STANDING_RECENTERING_IMPAIRED", "standing_recentering", "Difficulty recentering in standing", "The patient did not return to a stable centered standing position.", "moderate", "PASS; task-specific balance observation", "SUPPORTED_STANDING_CONTROL")},
        ],
    },
    {
        "id": "B5",
        "title": "Supported Step-Stance Hold",
        "view": "45-degree view",
        "focus": "Narrowed base balance, anticipatory control and step stability",
        "safety_tier": "spotter_required",
        "safety_note": "Attempt only after supported standing and weight shift are safe.",
        "steps": [
            {"id": "B5-S1", "voice": "Stand with support and place the affected foot a short step forward.", "target": {"x": 0.56, "y": 0.80, "r": 0.16, "landmark": "AFFECTED_FOOT_FORWARD"}, "hold_ms": 1200, "caption": "Place the affected foot forward", "failure_phenotype": _phenotype("STEP_STANCE_ENTRY_IMPAIRED", "step_stance_entry", "Difficulty entering step stance", "The affected foot did not reach the short forward step position.", "severe", "Berg Balance Scale task concepts; observational gait analysis", "GAIT_INITIATION_IMPAIRED")},
            {"id": "B5-S2", "voice": "Keep the support and hold this step position without moving your feet.", "target": {"x": 0.5, "y": 0.52, "r": 0.16, "landmark": "STEP_STANCE_STABLE"}, "hold_ms": 2500, "movement_required": False, "caption": "Hold supported step stance", "measure": ["step_stance_sway", "foot_position_stability"], "failure_phenotype": _phenotype("STEP_STANCE_BALANCE_IMPAIRED", "step_stance_balance", "Impaired balance in step stance", "The patient could not maintain the supported step position steadily.", "severe", "Berg Balance Scale task concepts", "DYNAMIC_BALANCE_IMPAIRED")},
            {"id": "B5-S3", "voice": "Bring the affected foot back beside the other foot and settle in the middle.", "target": {"x": 0.5, "y": 0.82, "r": 0.15, "landmark": "AFFECTED_FOOT_RETURNED"}, "hold_ms": 1200, "caption": "Return to parallel stance", "failure_phenotype": _phenotype("STEP_STANCE_EXIT_IMPAIRED", "step_stance_exit", "Difficulty leaving step stance", "The affected foot did not return to parallel stance with control.", "moderate", "Task-specific balance observation", "DYNAMIC_BALANCE_IMPAIRED")},
        ],
    },
]


def attach_hand_failure_phenotypes(hand_tasks: List[Dict[str, Any]]) -> None:
    """Attach hand phenotypes without rewriting the retained hand task content."""
    for task in hand_tasks:
        for step in task.get("steps", []):
            phenotype = HAND_STEP_PHENOTYPES.get(step["id"])
            if phenotype:
                step["failure_phenotype"] = phenotype
