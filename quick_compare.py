"""Weighted scoring for three pairwise comparisons."""

import hashlib
import json

from model_validation import names
from utility_model import compare_options


TEMPLATES = {
    "Buying something": {
        "options": ["Option A", "Option B"],
        "criteria": ["Price", "Fit for your needs", "Convenience"],
        "questions": ["Which is better for your budget?", "Which meets your needs better?", "Which is easier to buy and use?"],
    },
    "Getting around": {
        "options": ["Taxi", "Public transit"],
        "criteria": ["Cost", "Time", "Comfort"],
        "questions": ["Which costs less?", "Which saves you more time?", "Which is more comfortable?"],
    },
    "Study & work": {
        "options": ["Option A", "Option B"],
        "criteria": ["Time commitment", "Fit for your goal", "Flexibility"],
        "questions": ["Which fits your available time?", "Which helps your goal more?", "Which fits around your other plans?"],
    },
    "Plans & places": {
        "options": ["Plan A", "Plan B"],
        "criteria": ["Cost", "Enjoyment", "Convenience"],
        "questions": ["Which is better for your budget?", "Which would you enjoy more?", "Which is easier to arrange?"],
    },
    "Allocating resources": {
        "options": ["Plan A", "Plan B"],
        "criteria": ["Cost", "Impact", "Feasibility"],
        "questions": ["Which uses fewer resources?", "Which helps your goal more?", "Which is easier to carry out?"],
    },
    "Something else": {
        "options": ["Option A", "Option B"],
        "criteria": ["Value", "Usefulness", "Convenience"],
        "questions": ["Which offers better value?", "Which is more useful to you?", "Which is easier for you?"],
    },
}


def compare_quick(options, criteria, answers, priority_index=None):
    names(options, "Options", 2)
    names(criteria, "Criteria", 3)
    if options[0].strip().casefold() == options[1].strip().casefold():
        raise ValueError("Give the two options different names.")
    if len({name.strip().casefold() for name in criteria}) != 3:
        raise ValueError("Give the three factors different names.")
    if not isinstance(answers, list) or len(answers) != 3:
        raise ValueError("Answer the three comparison questions.")
    if any(answer not in ("first", "same", "second") for answer in answers):
        raise ValueError("Choose an option or Similar for every question.")
    if priority_index is not None and (
        isinstance(priority_index, bool) or not isinstance(priority_index, int)
        or not 0 <= priority_index < 3
    ):
        raise ValueError("Choose a valid priority.")

    # These are preference votes, not measured differences between products.
    mapping = {"first": [100.0, 0.0], "same": [50.0, 50.0], "second": [0.0, 100.0]}
    scores = [list(mapping[answer]) for answer in answers]
    weights = [1.0, 1.0, 1.0]
    if priority_index is not None:
        # Normalizing 3:1:1 gives the documented 60% / 20% / 20% preset.
        weights[priority_index] = 3.0
    result = compare_options(options, scores, weights, criteria)
    result["score_label"] = "Priority match"
    result["answers"] = list(answers)
    result["priority_index"] = priority_index
    result["quick_assumptions"] = [
        "A preferred option gets 100 factor points and the other gets 0; Similar gives each 50.",
        "Balanced gives each factor equal weight. A selected priority receives 60%, with 20% for each other factor.",
        "These points summarize your comparisons. They do not measure how large the real-world differences are.",
    ]
    if result["is_tied"]:
        result["summary"] = "Your answers leave the options level. Try another priority or add details in Advanced model."
    else:
        winner = result["recommended_indices"][0]
        side = "first" if winner == 0 else "second"
        favored = [criterion for criterion, answer in zip(criteria, answers) if answer == side]
        result["summary"] = f"With your current priorities, {options[winner]} leads on {', '.join(favored).lower()}."
    return result


def build_quick_packet(category, options, criteria, answers, priority_index=None, is_example=False):
    result = compare_quick(options, criteria, answers, priority_index)
    weights = [1.0, 1.0, 1.0]
    if priority_index is not None:
        weights[priority_index] = 3.0
    inputs = {
        "question": f"{options[0]} or {options[1]}?", "category": category,
        "mode": "Compare options", "basis": "Weighted utility (0–100)",
        "strategies": list(options), "criteria": list(criteria),
        "criterion_scores": result["criterion_scores"], "weights": weights,
        "scenarios": None, "probabilities": None, "unit": "points",
        "score_label": "Priority match", "score_unit": "points",
    }
    encoded = json.dumps(inputs, sort_keys=True, ensure_ascii=False)
    return {"result": result, "inputs": inputs,
            "snapshot": hashlib.sha256(encoded.encode()).hexdigest(), "is_example": is_example}
