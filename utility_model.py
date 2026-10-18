"""Fixed-anchor scoring and weighted utility."""

import math
from copy import deepcopy

from decision_engine import analyze_decision
from model_validation import (
    DISCLAIMER, criterion_names as checked_criterion_names, matrix, names,
    nonempty_list, normalize_weights, number, same_value,
)


MODEL_ASSUMPTIONS = [
    "Scores use fixed, meaningful 0-100 utility scales; higher is better.",
    "Weights represent preferences, not scenario probabilities.",
    "The additive model assumes the chosen criteria can be meaningfully combined; avoid double-counting related factors.",
]


def score_value(value, zero_at, hundred_at):
    """Linear utility between two user-defined anchors, clipped to 0..100.

    For a cost criterion, zero_at is greater than hundred_at. Anchors never
    depend on which alternatives happen to be present in the comparison.
    """
    value = number(value, "Raw value")
    zero = number(zero_at, "Zero-score anchor")
    hundred = number(hundred_at, "Hundred-score anchor")
    if zero == hundred:
        raise ValueError("Scoring anchors must be different.")
    if hundred > zero:
        if value <= zero:
            return 0.0
        if value >= hundred:
            return 100.0
    else:
        if value >= zero:
            return 0.0
        if value <= hundred:
            return 100.0
    span = hundred - zero
    if math.isfinite(span):
        fraction = (value - zero) / span
    else:
        # Scale before subtracting only when the raw span would overflow.
        scale = max(abs(value), abs(zero), abs(hundred))
        fraction = ((value / scale) - (zero / scale)) / ((hundred / scale) - (zero / scale))
    return min(100.0, max(0.0, 100.0 * fraction))


def score_matrix(raw_values, zero_at, hundred_at):
    matrix(raw_values, "Raw values")
    # Validate the anchors even if all raw values would be clipped.
    score_value(raw_values[0][0], zero_at, hundred_at)
    return [[score_value(value, zero_at, hundred_at) for value in row]
            for row in raw_values]


def _prepare(criterion_matrices, weights):
    nonempty_list(criterion_matrices, "Criterion matrices")
    shape = None
    for values in criterion_matrices:
        current = matrix(values, "Criterion scores", minimum=0, maximum=100)
        if shape is None:
            shape = current
        if current != shape:
            raise ValueError("All criterion matrices must have the same shape.")
    normalized = normalize_weights(weights, len(criterion_matrices))
    return shape[0], shape[1], normalized


def _combine(criterion_matrices, normalized, rows, columns):
    # Sum unrounded contributions; rounding belongs in the displayed result.
    return [[min(100.0, max(0.0, math.fsum(
        normalized[k] * criterion_matrices[k][i][j]
        for k in range(len(normalized))
    ))) for j in range(columns)] for i in range(rows)]


def build_weighted_payoffs(criterion_matrices, weights):
    """Return U[i][j] from scores[k][i][j] and relative importance weights."""
    rows, columns, normalized = _prepare(criterion_matrices, weights)
    return _combine(criterion_matrices, normalized, rows, columns)


def analyze_weighted_decision(strategies, scenarios, criterion_matrices, weights,
                              criterion_names=None, probabilities=None):
    rows, columns, normalized = _prepare(criterion_matrices, weights)
    names(strategies, "Strategies", rows)
    names(scenarios, "Scenarios", columns)
    criteria = checked_criterion_names(criterion_names, len(normalized))
    payoffs = _combine(criterion_matrices, normalized, rows, columns)
    result = analyze_decision(strategies, scenarios, payoffs, probabilities)
    contributions = [
        [[normalized[k] * criterion_matrices[k][i][j] for j in range(columns)]
         for i in range(rows)] for k in range(len(normalized))
    ]
    result.update({
        "mode": "uncertain", "score_unit": "utility points",
        "utility_matrix": payoffs, "normalized_weights": normalized,
        "criteria": criteria, "criterion_matrices": deepcopy(criterion_matrices),
        "contributions": contributions,
        "weighting_formula": "U[i][j] = sum_k(weight[k] * score[k][i][j])",
        "regret_formula": "R[i][j] = max_a(U[a][j]) - U[i][j]",
        "decision_formula": "Choose all i minimizing max_j(R[i][j]).",
        "model_assumptions": list(MODEL_ASSUMPTIONS),
    })
    result["explanation"] += " Values are utility points; lower maximum regret is better."
    return result


def compare_options(strategies, criterion_scores, weights, criterion_names=None):
    """Static comparison. criterion_scores[k][i] has no scenario dimension."""
    count, options = matrix(criterion_scores, "Criterion scores", 0, 100)
    names(strategies, "Strategies", options)
    normalized = normalize_weights(weights, count)
    criteria = checked_criterion_names(criterion_names, count)
    contributions = [[normalized[k] * criterion_scores[k][i]
                      for i in range(options)] for k in range(count)]
    scores = [min(100.0, max(0.0, math.fsum(row[i] for row in contributions)))
              for i in range(options)]
    maximum = max(scores)
    indices = [i for i, score in enumerate(scores) if same_value(score, maximum)]
    recommended = [strategies[i] for i in indices]
    tied = len(indices) > 1
    calculations = []
    for i in range(options):
        terms = " + ".join(f"{normalized[k]:g} * {criterion_scores[k][i]:g}"
                           for k in range(count))
        calculations.append({"strategy_index": i, "strategy": strategies[i],
                             "score": scores[i], "formula": f"{terms} = {scores[i]:g}"})
    return {
        "mode": "static", "criterion": "maximum_weighted_utility",
        "scores": scores, "score_unit": "utility points",
        "recommended": recommended, "recommended_indices": indices,
        "is_tied": tied,
        "tie_message": "Multiple options share the highest overall fit within the numerical tolerance. A tie is a valid result." if tied else None,
        "criteria": criteria, "normalized_weights": normalized,
        "criterion_scores": deepcopy(criterion_scores),
        "contributions": contributions, "score_calculations": calculations,
        "explanation": f"Higher weighted utility is better. The highest overall fit is {maximum:g} utility points. Recommended: {', '.join(recommended)}.",
        "model_assumptions": list(MODEL_ASSUMPTIONS), "disclaimer": DISCLAIMER,
    }
