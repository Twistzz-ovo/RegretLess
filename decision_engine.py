"""Minimax regret and optional expected values for payoff matrices."""

import math

from model_validation import (
    ABS_TOLERANCE, DISCLAIMER, matrix, names, nonempty_list, number, same_value,
)


def calculate_regret_matrix(payoffs):
    rows, columns = matrix(payoffs, "Payoffs")
    # Rows are options; each column is one possible future scenario.
    best_payoffs = [max(row[j] for row in payoffs) for j in range(columns)]
    regrets = []
    for i in range(rows):
        row = []
        for j in range(columns):
            regret = best_payoffs[j] - payoffs[i][j]
            number(regret, "Calculated regret", minimum=0)
            row.append(regret)
        regrets.append(row)
    return regrets


def calculate_max_regrets(regret_matrix):
    matrix(regret_matrix, "Regret matrix", minimum=0)
    return [max(row) for row in regret_matrix]


def calculate_minimax_regret(strategies, max_regrets):
    names(strategies, "Strategies")
    nonempty_list(max_regrets, "Maximum regrets")
    if len(strategies) != len(max_regrets):
        raise ValueError("Each strategy must have one maximum regret.")
    for value in max_regrets:
        number(value, "Every maximum regret", minimum=0)
    minimum = min(max_regrets)
    # Retain every tied option rather than letting input order pick a winner.
    return [name for name, value in zip(strategies, max_regrets)
            if same_value(value, minimum)]


def validate_probabilities(probabilities, scenarios):
    names(scenarios, "Scenarios")
    nonempty_list(probabilities, "Probabilities")
    if len(probabilities) != len(scenarios):
        raise ValueError("Each scenario must have one probability.")
    checked = [number(value, "Every probability", 0, 1) for value in probabilities]
    if not math.isclose(math.fsum(checked), 1.0, rel_tol=0.0,
                        abs_tol=ABS_TOLERANCE):
        raise ValueError("Probabilities must sum to 1.")


def calculate_expected_values(payoffs, probabilities):
    _, columns = matrix(payoffs, "Payoffs")
    validate_probabilities(probabilities, [f"Scenario {j + 1}" for j in range(columns)])
    result = []
    for row in payoffs:
        try:
            value = math.fsum(probability * payoff
                              for probability, payoff in zip(probabilities, row))
        except OverflowError:
            raise ValueError("Calculated expected value must be finite.") from None
        number(value, "Calculated expected value")
        result.append(value)
    return result


def classify_regret_risk(max_regrets, low_threshold, medium_threshold):
    # These bands reflect the user's thresholds, not universal risk categories.
    low = number(low_threshold, "Low threshold", minimum=0)
    medium = number(medium_threshold, "Medium threshold", minimum=0)
    if low >= medium:
        raise ValueError("Thresholds must satisfy 0 <= low threshold < medium threshold.")
    nonempty_list(max_regrets, "Maximum regrets")
    levels = []
    for value in max_regrets:
        number(value, "Every maximum regret", minimum=0)
        levels.append("Low" if value <= low else "Medium" if value <= medium else "High")
    return levels


def analyze_decision(strategies, scenarios, payoffs, probabilities=None):
    names(strategies, "Strategies")
    names(scenarios, "Scenarios")
    rows, columns = matrix(payoffs, "Payoffs")
    if rows != len(strategies):
        raise ValueError("Each strategy must have one payoff row.")
    if columns != len(scenarios):
        raise ValueError("Each payoff row must match the number of scenarios.")

    regret_matrix = calculate_regret_matrix(payoffs)
    max_regrets = calculate_max_regrets(regret_matrix)
    minimum = min(max_regrets)
    recommended_indices = [i for i, value in enumerate(max_regrets)
                           if same_value(value, minimum)]
    recommended = [strategies[i] for i in recommended_indices]
    # Missing probabilities stay missing; minimax regret does not need them.
    expected_values = None
    if probabilities is not None:
        validate_probabilities(probabilities, scenarios)
        expected_values = calculate_expected_values(payoffs, probabilities)

    best_payoffs = [max(row[j] for row in payoffs) for j in range(columns)]
    best_strategy_indices = [
        [i for i in range(rows) if same_value(payoffs[i][j], best_payoffs[j])]
        for j in range(columns)
    ]
    worst_indices = [[j for j, value in enumerate(row) if same_value(value, max_regrets[i])]
                     for i, row in enumerate(regret_matrix)]
    calculations = []
    for i in range(rows):
        calculations.append([
            {"strategy_index": i, "scenario_index": j,
             "strategy": strategies[i], "scenario": scenarios[j],
             "best_payoff": best_payoffs[j], "payoff": payoffs[i][j],
             "regret": regret_matrix[i][j],
             "formula": f"{best_payoffs[j]:g} - ({payoffs[i][j]:g}) = {regret_matrix[i][j]:g}"}
            for j in range(columns)
        ])
    is_tied = len(recommended) > 1
    tie_message = None
    if is_tied:
        tie_message = (
            "Multiple strategies share the lowest maximum regret within the numerical "
            "tolerance. A tie is a valid result. Consider additional relevant factors "
            "or refine your inputs before comparing again."
        )
    explanation = (
        "Regret is the gap from the highest payoff in the same scenario. "
        + " ".join(f"{strategy}: maximum regret = {value:g}."
                   for strategy, value in zip(strategies, max_regrets))
        + f" The lowest maximum regret is {minimum:g}. "
        + "Recommended under minimax regret: " + ", ".join(recommended) + "."
    )
    return {
        "regret_matrix": regret_matrix,
        "max_regrets": max_regrets,
        "recommended": recommended,
        "expected_values": expected_values,
        "explanation": explanation,
        "is_tied": is_tied,
        "tie_message": tie_message,
        "recommended_indices": recommended_indices,
        "scenario_best_payoffs": best_payoffs,
        "scenario_best_strategy_indices": best_strategy_indices,
        "worst_scenario_indices": worst_indices,
        "worst_scenarios": [[scenarios[j] for j in indices] for indices in worst_indices],
        "regret_calculations": calculations,
        "criterion": "minimax_regret",
        "tie_tolerance": {"absolute": ABS_TOLERANCE, "relative": 0.0,
                          "integer_comparisons": "exact"},
        "disclaimer": DISCLAIMER,
    }


if __name__ == "__main__":
    from pprint import pprint

    print("Hypothetical bubble tea shop example:")
    pprint(analyze_decision(
        ["Downtown", "Residential"], ["Boom", "Normal", "Slump"],
        [[12000, 3000, -6000], [7000, 4000, -1000]],
    ))
