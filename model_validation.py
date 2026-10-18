"""Input checks and numerical comparisons."""

import math


ABS_TOLERANCE = 1e-9
DISCLAIMER = "Based on your inputs and preferences. Scores are not probabilities or guarantees. For reference only."


def number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number.")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f"{label} must be a finite, representable number.") from None
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite.")
    if minimum is not None and result < minimum:
        raise ValueError(f"{label} must be at least {minimum}.")
    if maximum is not None and result > maximum:
        raise ValueError(f"{label} must be at most {maximum}.")
    return result


def nonempty_list(values, label):
    if not isinstance(values, list) or not values:
        raise ValueError(f"{label} must be a non-empty list.")


def names(values, label, count=None):
    nonempty_list(values, label)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"Every name in {label} must be a non-empty string.")
    if count is not None and len(values) != count:
        raise ValueError(f"{label} must contain {count} names.")


def matrix(values, label, minimum=None, maximum=None):
    nonempty_list(values, label)
    columns = None
    for row in values:
        nonempty_list(row, f"Each row in {label}")
        if columns is None:
            columns = len(row)
        if len(row) != columns:
            raise ValueError(f"All rows in {label} must have the same length.")
        for value in row:
            number(value, f"Every value in {label}", minimum, maximum)
    return len(values), columns


def same_value(left, right):
    # Preserve exact comparisons when both values are integers. For floats,
    # use one absolute tolerance in the original units; never round to compare.
    if isinstance(left, int) and isinstance(right, int):
        return left == right
    return math.isclose(left, right, rel_tol=0.0, abs_tol=ABS_TOLERANCE)


def normalize_weights(weights, count=None):
    nonempty_list(weights, "Weights")
    if count is not None and len(weights) != count:
        raise ValueError("Each criterion must have one weight.")
    checked = [number(value, "Every weight", minimum=0) for value in weights]
    largest = max(checked)
    if largest == 0:
        raise ValueError("At least one weight must be greater than zero.")
    # Scaling first prevents overflow for large, otherwise valid weights.
    scaled = [value / largest for value in checked]
    total = math.fsum(scaled)
    return [value / total for value in scaled]


def criterion_names(values, count):
    if values is None:
        return [f"Criterion {index + 1}" for index in range(count)]
    names(values, "Criteria", count)
    return list(values)
