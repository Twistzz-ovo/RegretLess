"""Recalculate rankings while varying one criterion weight."""

import hashlib
import json
import math
from copy import deepcopy

from model_validation import nonempty_list, normalize_weights, number
from utility_model import analyze_weighted_decision, compare_options


def reallocate_weights(weights, criterion_index, new_weight):
    baseline = normalize_weights(weights)
    if isinstance(criterion_index, bool) or not isinstance(criterion_index, int):
        raise ValueError("Criterion index must be an integer.")
    if not 0 <= criterion_index < len(baseline):
        raise ValueError("Criterion index is out of range.")
    chosen = number(new_weight, "Selected weight", 0, 1)
    others = [i for i in range(len(baseline)) if i != criterion_index]
    result = [0.0] * len(baseline)
    result[criterion_index] = chosen
    if chosen == 1:
        return result
    if not others:
        raise ValueError("A model with one criterion must give it weight 1.")
    other_total = math.fsum(baseline[i] for i in others)
    if other_total == 0:
        raise ValueError("The other baseline weights are all zero. Assign their relative importance before reducing the selected weight.")
    # Preserve the other factors' relative importance as the selected weight moves.
    proportions = normalize_weights([baseline[i] for i in others])
    for i, proportion in zip(others, proportions):
        result[i] = (1.0 - chosen) * proportion
    return result


def _sample_weights(weights, criterion_index, weight_values):
    # Validate the index even when a caller supplies an empty or invalid grid.
    normalized = normalize_weights(weights)
    reallocate_weights(weights, criterion_index, normalized[criterion_index]
                       if isinstance(criterion_index, int) and not isinstance(criterion_index, bool)
                       and 0 <= criterion_index < len(normalized) else 1.0)
    if weight_values is None:
        weight_values = [1.0] if len(normalized) == 1 else [i / 100 for i in range(101)]
    nonempty_list(weight_values, "Sample weights")
    checked = [number(value, "Sample weight", 0, 1) for value in weight_values]
    if any(left >= right for left, right in zip(checked, checked[1:])):
        raise ValueError("Sample weights must be strictly increasing.")
    return checked


def _finish(baseline, points, snapshot, criterion_index):
    switches = []
    for left, right in zip(points, points[1:]):
        if left["recommended_indices"] != right["recommended_indices"]:
            switches.append({
                "from_weight": left["weight"], "to_weight": right["weight"],
                "from_recommended": left["recommended"], "to_recommended": right["recommended"],
                "exact": False,
            })
    serialized = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return {
        "mode": baseline["mode"], "criterion_index": criterion_index,
        "selected_criterion": baseline["criteria"][criterion_index],
        "baseline": baseline, "points": points,
        "switch_intervals": switches,
        "observed_tie_weights": [point["weight"] for point in points if point["is_tied"]],
        "snapshot_id": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "data_snapshot": deepcopy(snapshot),
        "method": "Sampled weight sensitivity; switch intervals are approximate, not analytic roots.",
        "explanation": "Scores and source data are fixed. Other weights keep their baseline proportions while the selected weight changes.",
        "disclaimer": baseline["disclaimer"],
    }


def analyze_weight_sensitivity(strategies, scenarios, criterion_matrices, weights,
                               criterion_index, weight_values=None,
                               criterion_names=None, probabilities=None):
    baseline = analyze_weighted_decision(
        strategies, scenarios, criterion_matrices, weights, criterion_names, probabilities)
    grid = _sample_weights(weights, criterion_index, weight_values)
    # Hold the scores fixed, so changes come from weights rather than new data.
    snapshot = {"strategies": list(strategies), "scenarios": list(scenarios),
                "criterion_matrices": deepcopy(criterion_matrices),
                "criteria": baseline["criteria"], "probabilities": deepcopy(probabilities)}
    points = []
    for weight in grid:
        changed = reallocate_weights(weights, criterion_index, weight)
        result = analyze_weighted_decision(
            snapshot["strategies"], snapshot["scenarios"], snapshot["criterion_matrices"],
            changed, baseline["criteria"], snapshot["probabilities"])
        points.append({"weight": weight, "normalized_weights": result["normalized_weights"],
                       "utility_matrix": result["utility_matrix"],
                       "max_regrets": result["max_regrets"],
                       "recommended": result["recommended"],
                       "recommended_indices": result["recommended_indices"],
                       "is_tied": result["is_tied"], "expected_values": result["expected_values"]})
    return _finish(baseline, points, snapshot, criterion_index)


def analyze_static_weight_sensitivity(strategies, criterion_scores, weights,
                                      criterion_index, weight_values=None,
                                      criterion_names=None):
    baseline = compare_options(strategies, criterion_scores, weights, criterion_names)
    grid = _sample_weights(weights, criterion_index, weight_values)
    snapshot = {"strategies": list(strategies), "criterion_scores": deepcopy(criterion_scores),
                "criteria": baseline["criteria"]}
    points = []
    for weight in grid:
        changed = reallocate_weights(weights, criterion_index, weight)
        result = compare_options(snapshot["strategies"], snapshot["criterion_scores"],
                                 changed, baseline["criteria"])
        points.append({"weight": weight, "normalized_weights": result["normalized_weights"],
                       "scores": result["scores"], "recommended": result["recommended"],
                       "recommended_indices": result["recommended_indices"], "is_tied": result["is_tied"]})
    return _finish(baseline, points, snapshot, criterion_index)
