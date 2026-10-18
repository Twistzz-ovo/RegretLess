"""Detailed inputs, model results, and weight exploration."""

import hashlib
import math
import numbers

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from cases import get_case_template
from data_sources import FreeDataClient
from decision_engine import analyze_decision, classify_regret_risk
from model_validation import normalize_weights
from sensitivity import analyze_static_weight_sensitivity, analyze_weight_sensitivity
from utility_model import analyze_weighted_decision, compare_options, score_value


CATEGORIES = [
    "Buying & replacing", "Travel & places", "Study & work",
    "Events & plans", "Resource allocation", "Custom",
]
MODES = ["Compare options", "Explore uncertain futures"]
SCORE_TYPES = ["Direct utility scores", "Measured values with anchors"]
STATIC_COLUMN = "Value"
COLORS = ["#2e6070", "#b85c38", "#558571", "#76628c", "#9d7b32", "#4873a2"]


def identity(*parts):
    return hashlib.sha256(repr(parts).encode("utf-8")).hexdigest()[:16]


def format_number(value, unit=""):
    return f"{value:,.2f}{' ' + unit if unit else ''}"


def restore_widget_value(key, value):
    """Restore a widget from permanent input state after another page hides it."""
    if key not in st.session_state:
        st.session_state[key] = value


def initialize_state():
    defaults = {
        "strategies": [], "scenarios": [], "criteria": [], "factor_specs": {},
        "entered_values": {}, "raw_payoffs": {}, "analysis_packet": None,
        "context": {"category": CATEGORIES[0], "question": "", "mode": MODES[0],
                    "basis": "Weighted utility (0–100)", "unit": "", "direction": "Higher is better",
                    "probability_text": ""},
        "reference_result": None,
        "threshold_settings": {},
        "reduce_motion": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    # Migrate saved payoff values from earlier sessions.
    if "payoff_values" in st.session_state:
        for (option, scenario), value in st.session_state.payoff_values.items():
            st.session_state.entered_values.setdefault(("original_payoffs", option, scenario), value)


def load_laptop_demo():
    """Load the laptop example into the advanced form."""
    case = get_case_template("laptop")
    # Clear editor deltas before rebuilding widgets; otherwise old edits are reapplied.
    prefixes = ("weight_", "kind_", "zero_meaning_", "hundred_meaning_",
                "unit_", "zero_at_", "hundred_at_", "editor_", "lab_slider_")
    for key in list(st.session_state):
        if key.startswith(prefixes):
            del st.session_state[key]
    context = {"category": CATEGORIES[0], "question": "Which laptop should I choose?",
               "mode": MODES[1], "basis": "Weighted utility (0–100)", "unit": "",
               "direction": "Higher is better", "probability_text": ""}
    st.session_state.context = context
    for key, value in {
        "decision_category": context["category"], "decision_question": context["question"],
        "analysis_mode": context["mode"], "outcome_basis": context["basis"],
        "outcome_unit": "", "outcome_direction": context["direction"], "probability_entry": "",
    }.items():
        st.session_state[key] = value
    st.session_state.strategies = case["strategies"]
    st.session_state.scenarios = case["scenarios"]
    st.session_state.criteria = case["criteria"]
    st.session_state.factor_specs = {
        name: {"weight": float(weight), "kind": SCORE_TYPES[0],
               "zero_meaning": case["score_meaning"]["0"],
               "hundred_meaning": case["score_meaning"]["100"],
               "zero_at": 100.0, "hundred_at": 0.0, "unit": ""}
        for name, weight in zip(case["criteria"], [40, 60])
    }
    st.session_state.entered_values = {
        ((name, "utility", "future"), option, scenario): float(case["criterion_matrices"][k][i][j])
        for k, name in enumerate(case["criteria"])
        for i, option in enumerate(case["strategies"])
        for j, scenario in enumerate(case["scenarios"])
    }
    st.session_state.analysis_packet = None
    st.session_state.raw_payoffs = {}
    st.session_state.demo_run_pending = case["assumption_notice"]
    st.session_state.active_analysis = "advanced"


def add_or_remove_names(state_key, title, singular, placeholder):
    st.subheader(title)
    with st.form(f"add_{state_key}", clear_on_submit=True):
        text = st.text_input(f"New {singular.lower()}", placeholder=placeholder)
        submitted = st.form_submit_button(f"Add {singular}")
    if submitted:
        name = text.strip()
        if not name:
            st.warning(f"Enter a {singular.lower()} name.")
        elif any(old.casefold() == name.casefold() for old in st.session_state[state_key]):
            st.warning(f"This {singular.lower()} already exists.")
        else:
            st.session_state[state_key].append(name)
            if state_key == "criteria":
                st.session_state.factor_specs[name] = {
                    "weight": 1.0, "kind": SCORE_TYPES[0], "zero_meaning": "Very poor fit",
                    "hundred_meaning": "Excellent fit", "zero_at": 100.0,
                    "hundred_at": 0.0, "unit": "",
                }
            st.rerun()
    if not st.session_state[state_key]:
        st.caption(f"No {title.lower()} added yet.")
    for index, name in enumerate(st.session_state[state_key]):
        left, right = st.columns([5, 1])
        left.write(name)
        if right.button("Remove", key=f"remove_{state_key}_{identity(name)}"):
            st.session_state[state_key].pop(index)
            if state_key == "criteria":
                st.session_state.factor_specs.pop(name, None)
            st.rerun()


def edit_numbers(tag, option_names, column_names, initial, minimum=None, maximum=None):
    """Read option-by-scenario values from an editable table."""
    state = st.session_state.entered_values
    values = [
        [state.get((tag, option, column), initial) for column in column_names]
        for option in option_names
    ]
    frame = pd.DataFrame(values, index=option_names, columns=column_names)
    frame.index.name = "Option"
    edited = st.data_editor(
        frame, hide_index=False, num_rows="fixed", width="stretch",
        key="editor_" + identity(tag, option_names, column_names),
        column_config={column: st.column_config.NumberColumn(
            column, min_value=minimum, max_value=maximum, format="%.2f"
        ) for column in column_names},
    )
    output = []
    for option in option_names:
        row = []
        for column in column_names:
            value = edited.loc[option, column]
            state[(tag, option, column)] = value
            if isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(value):
                raise ValueError("Every table cell must contain a finite number.")
            if minimum is not None and value < minimum or maximum is not None and value > maximum:
                raise ValueError("Every utility score must be between 0 and 100.")
            row.append(float(value))
        output.append(row)
    return output


def factor_input(name, options, scenarios):
    """Return a strategy-by-scenario matrix of utility scores for this factor."""
    specs = st.session_state.factor_specs
    spec = specs[name]
    token = identity(name)
    with st.expander(name, expanded=True):
        first, second = st.columns(2)
        spec["weight"] = first.number_input(
            "Relative importance", min_value=0.0, step=1.0,
            value=float(spec["weight"]), key=f"weight_{token}",
            help="Weights are relative. For example, 2 and 1 become 67% and 33%.",
        )
        spec["kind"] = second.selectbox(
            "Input type", SCORE_TYPES, index=SCORE_TYPES.index(spec["kind"]),
            key=f"kind_{token}",
        )
        meanings = st.columns(2)
        spec["zero_meaning"] = meanings[0].text_input(
            "What does 0 mean?", value=spec["zero_meaning"], key=f"zero_meaning_{token}"
        )
        spec["hundred_meaning"] = meanings[1].text_input(
            "What does 100 mean?", value=spec["hundred_meaning"],
            key=f"hundred_meaning_{token}",
        )
        if not spec["zero_meaning"].strip() or not spec["hundred_meaning"].strip():
            raise ValueError(f"Describe both ends of the 0–100 scale for {name}.")

        measured = spec["kind"] == SCORE_TYPES[1]
        if measured:
            unit_col, zero_col, hundred_col = st.columns(3)
            spec["unit"] = unit_col.text_input(
                "Measurement unit", value=spec["unit"], placeholder="e.g. CAD or minutes",
                key=f"unit_{token}",
            )
            spec["zero_at"] = zero_col.number_input(
                "Raw value worth 0 points", value=float(spec["zero_at"]),
                key=f"zero_at_{token}",
            )
            spec["hundred_at"] = hundred_col.number_input(
                "Raw value worth 100 points", value=float(spec["hundred_at"]),
                key=f"hundred_at_{token}",
            )
            st.caption("Your fixed anchors set a linear 0–100 scale. Values outside the anchors are clipped. Confirm that this rule matches your preference.")
        columns = scenarios if scenarios is not None else [STATIC_COLUMN]
        if not options or not columns:
            st.info("Add options and, in the futures mode, scenarios to enter scores.")
            return None
        st.caption("Rows are options. " + ("Columns are future scenarios." if scenarios else "Enter a value for each option."))
        rows = edit_numbers(
            (name, "raw" if measured else "utility", "future" if scenarios else "static"),
            options, columns, 0.0 if measured else 50.0,
            minimum=None if measured else 0.0, maximum=None if measured else 100.0,
        )
        if measured:
            # Convert measurements using the same fixed anchors for every option.
            converted = [[score_value(value, spec["zero_at"], spec["hundred_at"])
                          for value in row] for row in rows]
            st.caption("Converted utility points (used by the analysis):")
            st.dataframe(pd.DataFrame(converted, index=options, columns=columns), width="stretch")
            return converted
        return rows


def read_probabilities(scenarios):
    st.subheader("Scenario probabilities · optional")
    st.caption("Leave blank when probabilities are unknown. Enter one number per scenario in the displayed order; they must total 1.")
    context = st.session_state.context
    text = st.text_input(
        "Probabilities", value=context["probability_text"],
        placeholder="e.g. 0.2, 0.5, 0.3", key="probability_entry",
    )
    context["probability_text"] = text
    if not text.strip():
        return None
    try:
        values = [float(part.strip()) for part in text.split(",")]
    except ValueError:
        raise ValueError("Use comma-separated numbers for scenario probabilities.") from None
    if len(values) != len(scenarios):
        raise ValueError("Enter exactly one probability for each scenario.")
    if not all(math.isfinite(value) and 0 <= value <= 1 for value in values):
        raise ValueError("Every scenario probability must be between 0 and 1.")
    if not math.isclose(math.fsum(values), 1, abs_tol=1e-9, rel_tol=0):
        raise ValueError("Scenario probabilities must add up to 1.")
    return values


@st.cache_resource
def reference_client():
    return FreeDataClient()


def data_and_context():
    with st.expander("Data & Context · optional"):
        st.write("Free public data can provide context. Confirm each source and choose your own scoring anchors before using any value in the analysis.")
        source_type = st.selectbox(
            "Reference source", ["City search", "Weather", "Air quality", "Exchange rate", "Book search"]
        )
        if source_type in ("City search", "Book search"):
            query = st.text_input("Search term", key="reference_query")
            request_parameters = {"query": query.strip()}
        elif source_type in ("Weather", "Air quality"):
            a, b = st.columns(2)
            latitude = a.number_input("Latitude", value=43.65, min_value=-90.0, max_value=90.0)
            longitude = b.number_input("Longitude", value=-79.38, min_value=-180.0, max_value=180.0)
            request_parameters = {"latitude": latitude, "longitude": longitude}
        else:
            a, b = st.columns(2)
            base = a.text_input("Base currency", value="CAD")
            quote = b.text_input("Quote currency", value="USD")
            request_parameters = {"base": base.strip().upper(), "quote": quote.strip().upper()}
        request_id = identity(source_type, request_parameters)
        if st.button("Look up reference data"):
            try:
                client = reference_client()
                if source_type == "City search":
                    response = client.search_cities(query)
                elif source_type == "Weather":
                    response = client.weather_forecast(latitude, longitude, days=3)
                elif source_type == "Air quality":
                    response = client.air_quality(latitude, longitude, days=1)
                elif source_type == "Exchange rate":
                    response = client.exchange_rate(base.strip().upper(), quote.strip().upper())
                else:
                    response = client.search_books(query)
                st.session_state.reference_result = (source_type, request_id, response)
            except (ValueError, OSError) as error:
                st.session_state.reference_result = (source_type, request_id, {"ok": False, "error": str(error)})
        saved = st.session_state.reference_result
        response = saved[2] if saved and len(saved) == 3 and saved[1] == request_id else None
        if saved and saved[0] == source_type and response is None:
            st.caption("The lookup inputs have changed. Look up reference data again to see matching results.")
        if response:
            if response.get("ok"):
                st.write(response.get("data"))
                st.caption("Source: " + str(response.get("source", "Public source"))
                           + " · Retrieved: " + str(response.get("retrieved_at", "Not provided")))
                st.caption("Data type: " + str(response.get("kind", "Reference data"))
                           + (" · From cache" if response.get("from_cache") else ""))
                st.write("**Lookup:**", request_parameters)
                if response.get("unit") is not None:
                    st.write("**Units:**", response["unit"])
                if response.get("data_time") is not None:
                    st.write("**Data time / coverage:**", response["data_time"])
                if response.get("location") is not None:
                    st.write("**Requested location:**", response["location"])
                if response.get("has_missing_values"):
                    st.warning("Some values are missing. Do not treat missing values as zero.")
                if response.get("attribution"):
                    st.caption(response["attribution"])
                if response.get("source_url"):
                    st.link_button("View source", response["source_url"])
                st.info("Reference data is not a scenario probability or a utility score. Enter or confirm your own scores above.")
            else:
                st.warning(str(response.get("error", "Reference data is unavailable. Continue with manual input.")))
                st.caption("Manual entry remains available; no paid fallback is used.")


def chart_style(figure, height=370):
    figure.update_layout(
        height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#203548"), margin=dict(l=70, r=25, t=55, b=60),
        legend=dict(orientation="h", y=1.12),
        transition_duration=0 if st.session_state.reduce_motion else 250,
    )
    figure.update_xaxes(automargin=True, gridcolor="#dce4e9", zerolinecolor="#c3ced5")
    figure.update_yaxes(automargin=True, gridcolor="#dce4e9", zerolinecolor="#c3ced5")
    return figure


def recommendation(result, uncertain, unit):
    st.subheader("Recommendation")
    names = result["recommended"]
    title = "Lowest worst-case gap" if uncertain else "Highest overall fit"
    st.success(("Tied recommendations: " if len(names) > 1 else "Recommended option: ") + ", ".join(names))
    st.write(f"**Criterion:** {title}. " + result["explanation"])
    st.caption(result["disclaimer"])
    if result.get("is_tied") and result.get("tie_message"):
        st.info(result["tie_message"])
    if uncertain:
        st.caption(f"Worst-case gap — Lower is better. Unit: {unit}.")
    else:
        st.caption("Overall fit — Higher is better. Scale: 0–100 utility points.")


def contribution_chart(result, options, scenarios=None):
    st.subheader("Factor contributions")
    if scenarios:
        selected = st.selectbox("Scenario for the contribution chart", scenarios)
        j = scenarios.index(selected)
        contributions = [[row[j] for row in criterion] for criterion in result["contributions"]]
    else:
        contributions = result["contributions"]
    fig = go.Figure()
    for k, criterion in enumerate(result["criteria"]):
        fig.add_bar(
            x=options, y=contributions[k], name=criterion, marker_color=COLORS[k % len(COLORS)],
            hovertemplate=f"{criterion}: %{{y:.2f}} utility points<extra></extra>",
        )
    fig.update_layout(barmode="stack", yaxis=dict(title="Overall fit · utility points", range=[0, 100]),
                      xaxis_title="Option")
    st.plotly_chart(chart_style(fig), width="stretch", theme=None)
    st.caption("Each colored section is the factor's contribution to the 0–100 overall fit.")


def gap_formula(calculation, raw_lower):
    if raw_lower:
        return (f"{-calculation['payoff']:g} − ({-calculation['best_payoff']:g}) "
                f"= {calculation['regret']:g}")
    return calculation["formula"]


def regret_views(result, inputs, utility_mode, unit, snapshot):
    options, scenarios = inputs["strategies"], inputs["scenarios"]
    raw_lower = not utility_mode and inputs["direction"] == "Lower cost or time is better"
    st.subheader("Regret matrix")
    st.caption("Worst-case gap — Lower is better. Compare each option with the best option in the same scenario.")
    values = result["regret_matrix"]
    heatmap = go.Figure(data=go.Heatmap(
        z=values, x=scenarios, y=options, zmin=0, zmax=100 if utility_mode else None,
        colorscale=[[0, "#f3f6f8"], [0.5, "#b4ccd2"], [1, "#2e6070"]],
        text=values, texttemplate="%{text:.1f}",
        hovertemplate="Option: %{y}<br>Scenario: %{x}<br>Gap: %{z:.2f}<extra></extra>",
        colorbar=dict(title=unit),
    ))
    heatmap.update_layout(yaxis_autorange="reversed", xaxis_title="Scenario", yaxis_title="Option")
    st.plotly_chart(chart_style(heatmap, max(320, len(options) * 65 + 160)), width="stretch", theme=None)
    st.caption("Click a cell in this table to inspect its calculation:")
    table = pd.DataFrame(values, index=options, columns=scenarios)
    table.index.name = "Option"
    event = st.dataframe(
        table, width="stretch", on_select="rerun", selection_mode="single-cell",
        key="regret_cell_" + identity(snapshot),
    )
    cells = event.selection.cells
    if cells and cells[0][1] in scenarios and 0 <= cells[0][0] < len(options):
        i, scenario = cells[0]
        j = scenarios.index(scenario)
    else:
        i, j = 0, 0
    calculation = result["regret_calculations"][i][j]
    st.info(f"{options[i]} · {scenarios[j]}: {gap_formula(calculation, raw_lower)} {unit}. "
            + ("The first value is this option's measurement; the second is the lowest measurement in that scenario."
               if raw_lower else "The first value is the best outcome in that scenario; the second is this option's result."))

    st.subheader("Maximum regret")
    maximums = result["max_regrets"]
    bars = go.Figure(data=go.Bar(
        x=options, y=maximums,
        marker_color=["#b85c38" if i in result["recommended_indices"] else "#2e6070"
                      for i in range(len(options))],
        text=[format_number(value) for value in maximums], textposition="outside",
        hovertemplate=f"%{{x}}: %{{y:.2f}} {unit}<extra></extra>",
    ))
    bars.update_layout(xaxis_title="Option", yaxis=dict(
        title=f"Worst-case gap · {unit}",
        range=[0, 100] if utility_mode else [0, max(maximums) * 1.2 or 1],
    ))
    st.plotly_chart(chart_style(bars), width="stretch", theme=None)
    explanation_rows = []
    for option_index, option in enumerate(options):
        reasons = [gap_formula(result["regret_calculations"][option_index][scenario_index], raw_lower)
                   for scenario_index in result["worst_scenario_indices"][option_index]]
        explanation_rows.append({
            "Option": option, "Worst-case gap": format_number(maximums[option_index], unit),
            "Scenario(s)": ", ".join(result["worst_scenarios"][option_index]),
            "Why": "; ".join(reasons),
        })
    st.dataframe(pd.DataFrame(explanation_rows), hide_index=True, width="stretch")
    return i, j


def show_math(result, inputs, inspected=(0, 0)):
    with st.expander("How it works", expanded=True):
        st.caption("All numbers below come from this same analysis result.")
        st.caption("Displayed values may be rounded. Recommendations use the original, unrounded values.")
        options = inputs["strategies"]
        if result.get("mode") == "static":
            i = result["recommended_indices"][0]
            c = result["score_calculations"][i]
            formula = c["formula"].replace(" = ", " ≈ ")
            st.write(f"**1 · Weighted overall fit.** For {options[i]}: {formula} utility points.")
            st.write("**2 · Compare options.** " + "; ".join(
                f"{name}: {format_number(value)}" for name, value in zip(options, result["scores"])
            ) + " utility points. The highest overall fit is recommended; there are no future scenarios in this mode.")
            return
        i, j = inspected
        scenario = inputs["scenarios"][j]
        if result.get("mode") == "uncertain":
            parts = [
                f"({result['normalized_weights'][k]:.6g} × {result['criterion_matrices'][k][i][j]:.6g})"
                for k in range(len(result["criteria"]))
            ]
            st.write(f"**1 · Weighted overall fit.** {options[i]} in {scenario}: "
                     + " + ".join(parts) + f" ≈ {result['utility_matrix'][i][j]:.6g} utility points.")
        else:
            original_value = result["regret_calculations"][i][j]["payoff"]
            if inputs["direction"] == "Lower cost or time is better":
                original_value = -original_value
            explanation = (" Lower-is-better measurements are negated before the backend compares gaps."
                           if inputs["direction"] == "Lower cost or time is better" else "")
            st.write(f"**1 · Outcome in original units.** {options[i]} in {scenario}: "
                     f"{format_number(original_value, inputs['unit'])}.{explanation}")
        calc = result["regret_calculations"][i][j]
        raw_lower = result.get("mode") != "uncertain" and inputs["direction"] == "Lower cost or time is better"
        st.write(f"**2 · Same-scenario gap.** "
                 + ("This measurement − lowest measurement: " if raw_lower else "Best outcome − this outcome: ")
                 + f"{gap_formula(calc, raw_lower)} {inputs['unit']}.")
        row = ", ".join(format_number(value) for value in result["regret_matrix"][i])
        st.write(f"**3 · Worst-case gap for {options[i]}.** max({row}) = "
                 f"{format_number(result['max_regrets'][i], inputs['unit'])}.")
        st.write("**4 · Minimax regret.** " + ", ".join(result["recommended"]) +
                 f" has the lowest maximum gap: {format_number(min(result['max_regrets']), inputs['unit'])}.")


def optional_thresholds(result, options, utility_mode, unit):
    with st.expander("Optional gap thresholds"):
        token = identity(utility_mode, unit)
        settings = st.session_state.threshold_settings.setdefault(
            token, {"enabled": False, "low": None, "medium": None})
        enabled = st.checkbox("Assess gap levels", value=settings["enabled"], key="assess_" + token)
        settings["enabled"] = enabled
        if not enabled:
            st.write("Not assessed")
            return
        a, b = st.columns(2)
        maximum = 100.0 if utility_mode else None
        st.caption(f"Set your own acceptable gap boundaries in {unit}. These are your preferences, not universal risk standards.")
        low = a.number_input("Low threshold", min_value=0.0, max_value=maximum,
                             value=settings["low"], key="low_threshold_" + token)
        medium = b.number_input("Medium threshold", min_value=0.0, max_value=maximum,
                                value=settings["medium"], key="medium_threshold_" + token)
        settings.update(low=low, medium=medium)
        if low is None or medium is None:
            st.info("Enter both thresholds to assess gap levels.")
            return
        try:
            levels = classify_regret_risk(result["max_regrets"], low, medium)
        except ValueError as error:
            st.warning(str(error))
        else:
            st.dataframe(pd.DataFrame({"Option": options, "Assessment": levels}),
                         hide_index=True, width="stretch")
            st.caption("These labels do not change the mathematical recommendation.")


def display_results(packet):
    result, inputs = packet["result"], packet["inputs"]
    options = inputs["strategies"]
    uncertain = inputs["mode"] == MODES[1]
    utility_mode = inputs["basis"] == "Weighted utility (0–100)"
    unit = "utility points" if utility_mode else inputs["unit"]
    st.divider()
    recommendation(result, uncertain, unit)
    if utility_mode:
        st.caption("Normalized importance: " + " · ".join(
            f"{name} {weight:.1%}" for name, weight in zip(result["criteria"], result["normalized_weights"])
        ))
        contribution_chart(result, options, inputs["scenarios"] if uncertain else None)
    if uncertain:
        inspected = regret_views(result, inputs, utility_mode, unit, packet["snapshot"])
        show_math(result, inputs, inspected)
        if result["expected_values"] is not None:
            st.subheader("Expected value · probabilities provided")
            lower_measurement = not utility_mode and inputs["direction"] == "Lower cost or time is better"
            displayed_values = ([-value for value in result["expected_values"]]
                                if lower_measurement else result["expected_values"])
            column_name = "Expected measurement (lower is better)" if lower_measurement else "Expected value"
            st.dataframe(pd.DataFrame({"Option": options, column_name: displayed_values}),
                         hide_index=True, width="stretch")
            st.caption("Expected values use only the scenario probabilities you entered. Original-unit measurements are shown in their original direction. Probabilities do not change the minimax recommendation.")
        else:
            st.caption("Expected value: Not assessed — no scenario probabilities were provided.")
        # Gap labels do not affect the ranking.
        optional_thresholds(result, options, utility_mode, unit)
    else:
        st.subheader("Overall fit")
        chart = go.Figure(data=go.Bar(
            x=options, y=result["scores"],
            marker_color=["#b85c38" if i in result["recommended_indices"] else "#2e6070"
                          for i in range(len(options))],
            text=[format_number(v) for v in result["scores"]], textposition="outside",
        ))
        chart.update_layout(yaxis=dict(title="Overall fit · utility points", range=[0, 100]), xaxis_title="Option")
        st.plotly_chart(chart_style(chart), width="stretch", theme=None)
        show_math(result, inputs)


def main_page():
    st.html("""
    <div class="rl-hero"><div class="rl-kicker">MODEL SETUP</div>
      <div class="rl-title">RegretLess<span>.</span></div>
      <div class="rl-subtitle">Compare outcomes and test your priorities.</div>
      <div class="rl-description">Enter a decision model, or load the laptop example below.</div>
    </div>""")
    with st.expander("Ready-made modeling demo"):
        st.write("Use a hypothetical laptop example to explore Minimax Regret without entering a matrix.")
        st.caption("Loads and analyzes sample inputs, replacing the current advanced setup.")
        st.button("Load laptop demo", on_click=load_laptop_demo)
    context = st.session_state.context
    restore_widget_value("decision_category", context["category"])
    restore_widget_value("decision_question", context["question"])
    restore_widget_value("analysis_mode", context["mode"])
    category = st.selectbox("Decision category", CATEGORIES, key="decision_category")
    question = st.text_input("Your decision question", placeholder="What should I choose?",
                             key="decision_question")
    mode = st.radio("Analysis mode", MODES, horizontal=True, key="analysis_mode")
    context.update(category=category, question=question, mode=mode)
    st.caption("Based on your inputs and preferences. Scores are not probabilities or guarantees. For reference only.")

    add_or_remove_names("strategies", "Options", "Option", "Name an option")
    options = list(st.session_state.strategies)
    scenarios = None
    basis = "Weighted utility (0–100)"
    if mode == MODES[1]:
        add_or_remove_names("scenarios", "Future scenarios", "Scenario", "Name a possible future")
        scenarios = list(st.session_state.scenarios)
        basis_options = ["Weighted utility (0–100)", "Original-unit payoffs"]
        restore_widget_value("outcome_basis", context["basis"])
        basis = st.radio("Outcome input", basis_options, horizontal=True, key="outcome_basis")
        context["basis"] = basis

    valid = True
    issue = None
    probabilities = None
    factors = []
    weights = []
    criteria = []
    raw_payoffs = None
    direction = "Higher is better"
    unit = "utility points"
    if mode == MODES[0] or basis == "Weighted utility (0–100)":
        add_or_remove_names("criteria", "Factors", "Factor", "e.g. Comfort or budget fit")
        criteria = list(st.session_state.criteria)
        if not criteria:
            valid, issue = False, "Add at least one factor."
        for name in criteria:
            try:
                scores = factor_input(name, options, scenarios)
                factors.append(scores)
            except ValueError as error:
                factors.append(None)
                valid, issue = False, str(error)
            weights.append(st.session_state.factor_specs[name]["weight"])
        if criteria:
            try:
                normalized = normalize_weights(weights, len(criteria))
                st.write("**Normalized importance:** " + " · ".join(
                    f"{name} {weight:.1%}" for name, weight in zip(criteria, normalized)
                ))
            except ValueError as error:
                valid, issue = False, str(error)
        if any(item is None for item in factors):
            valid = False
    else:
        st.subheader("Payoff matrix · original units")
        st.caption("Enter real amounts or measurements in one unit. This mode compares the measured outcomes directly; it does not mix them with utility scores.")
        u, d = st.columns(2)
        restore_widget_value("outcome_unit", context["unit"])
        restore_widget_value("outcome_direction", context["direction"])
        unit = u.text_input("Unit", key="outcome_unit", placeholder="e.g. CAD or minutes")
        direction_options = ["Higher is better", "Lower cost or time is better"]
        direction = d.radio("Direction", direction_options, key="outcome_direction")
        context.update(unit=unit, direction=direction)
        if not unit.strip():
            valid, issue = False, "Enter the unit used by every outcome, such as CAD or minutes."
        if options and scenarios:
            try:
                raw_payoffs = edit_numbers("original_payoffs", options, scenarios, 0.0)
            except ValueError as error:
                valid, issue = False, str(error)
        else:
            valid, issue = False, "Add an option and a scenario before entering outcomes."
        if direction == "Lower cost or time is better":
            st.caption("For a lower-is-better input, the outcome is negated before the backend compares gaps. The displayed gap keeps your original unit.")

    if mode == MODES[1]:
        try:
            probabilities = read_probabilities(scenarios)
        except ValueError as error:
            valid, issue = False, str(error)
    if not options:
        valid, issue = False, "Add at least one option."
    if mode == MODES[1] and not scenarios:
        valid, issue = False, "Add at least one future scenario."
    if issue:
        st.warning(issue)
    if basis == "Weighted utility (0–100)":
        st.caption("Hypothetical scores and weights. Replace example values with your own assumptions.")
    else:
        st.caption("Enter your own measured outcomes in the same unit for every option.")

    inputs = {
        "category": category, "question": question, "mode": mode, "basis": basis,
        "strategies": options, "scenarios": scenarios, "criteria": criteria,
        "weights": weights, "factors": factors, "raw_payoffs": raw_payoffs,
        "direction": direction, "unit": unit,
        "probabilities": probabilities, "probability_text": context["probability_text"],
        "factor_specs": {name: dict(st.session_state.factor_specs[name]) for name in criteria},
    }
    snapshot = identity(inputs)
    st.divider()
    pending_demo = st.session_state.pop("demo_run_pending", None)
    requested = st.button("Analyze Decision", type="primary")
    if requested or pending_demo:
        if not valid:
            st.warning("Correct the inputs above, then analyze again.")
        else:
            try:
                if mode == MODES[0]:
                    static_scores = [[row[0] for row in matrix] for matrix in factors]
                    result = compare_options(options, static_scores, weights, criteria)
                    inputs["criterion_scores"] = static_scores
                elif basis == "Weighted utility (0–100)":
                    result = analyze_weighted_decision(
                        options, scenarios, factors, weights, criteria, probabilities
                    )
                    inputs["criterion_matrices"] = factors
                else:
                    payoff_matrix = [[-value if direction == "Lower cost or time is better" else value
                                      for value in row] for row in raw_payoffs]
                    result = analyze_decision(options, scenarios, payoff_matrix, probabilities)
                st.session_state.analysis_packet = {
                    "result": result, "inputs": inputs, "snapshot": snapshot,
                }
                if pending_demo:
                    st.session_state.analysis_packet["assumption_notice"] = pending_demo
            except ValueError as error:
                st.session_state.analysis_packet = None
                st.error(f"Analysis could not run: {error}")
    packet = st.session_state.analysis_packet
    if packet is not None and packet["snapshot"] != snapshot:
        st.session_state.analysis_packet = None
        packet = None
        st.info("Inputs have changed. Run Analyze Decision to update the result and Decision Lab.")
    if packet is not None and packet["snapshot"] == snapshot and valid:
        if packet.get("assumption_notice"):
            st.info(packet["assumption_notice"])
        display_results(packet)


def lab_page(packet=None):
    st.title("Decision Lab")
    st.write("Explore how your priorities change the result.")
    if packet is None:
        packet = st.session_state.analysis_packet
    if not packet:
        st.info("Set up a decision on RegretLess and click Analyze Decision first.")
        return
    inputs, baseline = packet["inputs"], packet["result"]
    if packet.get("assumption_notice"):
        st.info(packet["assumption_notice"])
    if not inputs["criteria"]:
        st.info("Weight sensitivity requires factors with 0–100 utility scores. The original-unit payoff mode has no factor weights to adjust.")
        return
    st.caption(f"Decision: {inputs['question'] or 'Untitled decision'} · {inputs['mode']}")
    st.caption("Scores and external data are held fixed while one preference weight changes.")
    criteria = inputs["criteria"]
    selected = st.selectbox("Factor to explore", criteria)
    k = criteria.index(selected)
    baseline_weight = baseline["normalized_weights"][k]
    if len(criteria) == 1:
        st.info("With one factor, its normalized weight is always 100%. Add another factor to explore trade-offs.")
        chosen_percent = 100
    else:
        chosen_percent = st.slider(
            "Try this factor's weight (%)", 0, 100, int(round(baseline_weight * 100)), 1,
            help="Other factors retain their proportions from the original decision.",
            key="lab_slider_" + identity(packet["snapshot"], selected),
        )
    try:
        if inputs["mode"] == MODES[0]:
            lab = analyze_static_weight_sensitivity(
                inputs["strategies"], inputs["criterion_scores"], inputs["weights"],
                k, criterion_names=criteria,
            )
            metric = "scores"
            y_label = inputs.get("score_label", "Overall fit") + " · " + inputs.get("score_unit", "utility points")
            lower_is_better = False
        else:
            lab = analyze_weight_sensitivity(
                inputs["strategies"], inputs["scenarios"], inputs["criterion_matrices"],
                inputs["weights"], k, criterion_names=criteria,
                probabilities=inputs["probabilities"],
            )
            metric = "max_regrets"
            y_label = "Worst-case gap · utility points"
            lower_is_better = True
    except ValueError as error:
        st.warning(f"Sensitivity analysis is unavailable: {error}")
        return
    points = lab["points"]
    selected_point = points[chosen_percent] if len(points) == 101 else min(
        points, key=lambda point: abs(point["weight"] - chosen_percent / 100)
    )
    st.success("Recommended at this weight: " + ", ".join(selected_point["recommended"]))
    st.caption(("Worst-case gap — Lower is better." if lower_is_better else
                inputs.get("score_label", "Overall fit") + " — Higher is better.") + " " + lab["explanation"])
    fig = go.Figure()
    for i, option in enumerate(inputs["strategies"]):
        fig.add_scatter(
            x=[point["weight"] * 100 for point in points],
            y=[point[metric][i] for point in points], name=option,
            mode="lines", line=dict(color=COLORS[i % len(COLORS)], width=3),
            hovertemplate=f"{option}<br>Weight: %{{x:.0f}}%<br>Value: %{{y:.2f}}<extra></extra>",
        )
    if math.isclose(chosen_percent, baseline_weight * 100, rel_tol=0, abs_tol=1e-9):
        fig.add_vline(x=chosen_percent, line_color="#b85c38",
                      annotation_text="Current / selected weight", annotation_position="top right")
    else:
        fig.add_vline(x=baseline_weight * 100, line_dash="dash", line_color="#8b9ea4",
                      annotation_text="Current weight", annotation_position="top left")
        fig.add_vline(x=chosen_percent, line_color="#b85c38",
                      annotation_text="Selected weight", annotation_position="top right")
    fig.update_layout(xaxis=dict(title=f"{selected} weight (%)", range=[0, 100]),
                      yaxis=dict(title=y_label, range=[0, 100]))
    st.plotly_chart(chart_style(fig, 480), width="stretch", theme=None)
    if lab["switch_intervals"]:
        st.subheader("Where the recommendation changes")
        for change in lab["switch_intervals"]:
            st.write(f"Approximately {change['from_weight']:.0%}–{change['to_weight']:.0%}: "
                     f"{', '.join(change['from_recommended'])} → {', '.join(change['to_recommended'])}.")
        st.caption("Intervals come from sampled weights; these are approximate ranges, not exact solutions.")
    else:
        st.caption("No change was observed at the sampled 1% weights; changes between samples are still possible.")
    st.caption(lab["disclaimer"])


