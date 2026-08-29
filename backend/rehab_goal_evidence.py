"""Versioned evidence snippets used by the rehabilitation goal rule engine.

This is a small, deterministic retrieval layer rather than an unrestricted
medical text generator. Every retrieved chunk keeps its source URL so a goal
can be audited and the library can later be replaced by a vector store.
"""

from typing import Any, Dict, Iterable, List, Set


EVIDENCE_LIBRARY: List[Dict[str, Any]] = [
    {
        "id": "NICE_NG236_GOALS",
        "title": "NICE NG236: stroke rehabilitation goal setting",
        "organization": "NICE",
        "year": 2023,
        "url": "https://www.nice.org.uk/guidance/ng236/chapter/Recommendations",
        "tags": ["stroke", "goal_setting", "short_term", "long_term", "person_centered", "shared_decision", "review"],
        "rules": [
            "Goals should be meaningful and relevant to the person.",
            "Goals should focus on activity and participation, be challenging but achievable, and include short- and long-term elements.",
            "Goals should be agreed with the person and reviewed regularly.",
        ],
    },
    {
        "id": "UK_STROKE_GUIDELINE_GOALS",
        "title": "National Clinical Guideline for Stroke: goal setting",
        "organization": "Intercollegiate Stroke Working Party",
        "year": 2023,
        "url": "https://www.strokeguideline.org/chapter/rehabilitation-and-recovery-principles-of-rehabilitation/",
        "tags": ["stroke", "goal_setting", "smart", "review", "multidisciplinary", "patient_priority"],
        "rules": [
            "Document specific, time-bound and measurable outcomes.",
            "Use consistent measures to evaluate achievement.",
            "Short-term goals should cover days or weeks and long-term goals weeks or months.",
            "Patient and family preferences should be included where appropriate.",
        ],
    },
    {
        "id": "VA_DOD_STROKE_REHAB_2024",
        "title": "VA/DoD Clinical Practice Guideline: Management of Stroke Rehabilitation",
        "organization": "US Department of Veterans Affairs and Department of Defense",
        "year": 2024,
        "url": "https://www.healthquality.va.gov/guidelines/Rehab/stroke/index.asp",
        "tags": ["stroke", "goal_setting", "assessment", "safety", "multidisciplinary", "review"],
        "rules": [
            "Use patient goals together with standardized assessment and clinical judgment.",
            "Reassess needs and progress across the rehabilitation pathway.",
            "Clinical practice guidelines support but do not replace clinician judgment.",
        ],
    },
    {
        "id": "AHA_ASA_STROKE_REHAB",
        "title": "AHA/ASA Guidelines for Adult Stroke Rehabilitation and Recovery",
        "organization": "American Heart Association/American Stroke Association",
        "year": 2016,
        "url": "https://professional.heart.org/en/guidelines-statements/guidelines-for-adult-stroke-rehabilitation-and-recoverye98",
        "tags": ["stroke", "upper_limb", "hand", "lower_limb", "balance", "walking", "adl", "task_specific"],
        "rules": [
            "Rehabilitation should be organized around functional activities and task-specific practice.",
            "Mobility, upper-limb function and activities of daily living require domain-appropriate assessment and training.",
            "Safety, assistance and the appropriate rehabilitation setting remain clinical decisions.",
        ],
    },
    {
        "id": "NICE_QS2_GOAL_REVIEW",
        "title": "NICE QS2: regular review of rehabilitation goals",
        "organization": "NICE",
        "year": 2016,
        "url": "https://www.nice.org.uk/guidance/QS2/chapter/Quality-statement-6-Regular-review-of-rehabilitation-goals",
        "tags": ["stroke", "goal_setting", "review", "patient_priority", "shared_decision", "family"],
        "rules": [
            "Review rehabilitation goals at regular intervals with the person and, where appropriate, family or carers.",
            "Revise goals when they are no longer relevant or when progress differs from expectation.",
        ],
    },
    {
        "id": "GAS_REHAB_REVIEW",
        "title": "Goal Attainment Scaling in rehabilitation: educational review",
        "organization": "Journal of Rehabilitation Medicine",
        "year": 2023,
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10301855/",
        "tags": ["goal_setting", "smart", "gas", "measurement", "review"],
        "rules": [
            "Define the expected outcome, time frame and measurement method before treatment.",
            "Use observable attainment levels and avoid vague improvement statements.",
            "Goals may require revision when the observed recovery pattern changes.",
        ],
    },
]


def retrieve_goal_evidence(tags: Iterable[str], top_k: int = 3) -> List[Dict[str, Any]]:
    """Return the most relevant evidence chunks using transparent tag overlap."""
    query: Set[str] = {str(tag).lower() for tag in tags if tag}
    ranked = []
    for chunk in EVIDENCE_LIBRARY:
        chunk_tags = {str(tag).lower() for tag in chunk["tags"]}
        overlap = query & chunk_tags
        score = len(overlap)
        if "goal_setting" in chunk_tags:
            score += 1
        if score:
            ranked.append((score, chunk["year"], chunk))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [
        {
            "id": chunk["id"],
            "source": f'{chunk["organization"]} ({chunk["year"]})',
            "title": chunk["title"],
            "organization": chunk["organization"],
            "year": chunk["year"],
            "url": chunk["url"],
            "rules": list(chunk["rules"]),
            "retrieval_score": score,
            "matched_tags": sorted(query & {str(tag).lower() for tag in chunk["tags"]}),
        }
        for score, _, chunk in ranked[:top_k]
    ]
