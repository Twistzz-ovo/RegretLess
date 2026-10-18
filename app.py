"""RegretLess Streamlit app."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import advanced_ui
from quick_compare import TEMPLATES, build_quick_packet


def default_draft(category):
    return {"options": ["", ""],
            "answers": [None, None, None], "priority": -1, "is_example": False}


def initialize():
    advanced_ui.initialize_state()
    for key, value in {
        "quick_drafts": {}, "quick_active_category": "Buying something",
        "quick_view": "setup", "quick_packet": None, "active_analysis": "quick",
        "simple_workspace": "RegretLess", "quick_form_epoch": 0, "quick_form_visible": False,
    }.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if "quick_name_placeholders" not in st.session_state:
        # Move untouched defaults out of existing drafts without clearing custom names.
        for category, draft in st.session_state.quick_drafts.items():
            defaults = TEMPLATES[category]["options"]
            draft["options"] = ["" if name == defaults[i] else name
                                for i, name in enumerate(draft["options"])]
        st.session_state.quick_form_visible = False
        st.session_state.quick_name_placeholders = True


def current_draft():
    category = st.session_state.quick_active_category
    return st.session_state.quick_drafts.setdefault(category, default_draft(category))


def form_key(name):
    return f"{name}_{st.session_state.quick_form_epoch}"


def save_current_draft():
    old = current_draft()
    updated = {
        "options": [st.session_state.get(form_key(f"quick_option_{i}"), old["options"][i]) for i in range(2)],
        "answers": [st.session_state.get(form_key(f"quick_answer_{i}"), old["answers"][i]) for i in range(3)],
        "priority": st.session_state.get(form_key("quick_priority"), old["priority"]),
        "is_example": old["is_example"],
    }
    if any(updated[key] != old[key] for key in ("options", "answers", "priority")):
        updated["is_example"] = False
        st.session_state.quick_packet = None
    old.update(updated)


def restore_draft_widgets(draft, force=False):
    values = {"quick_priority": draft["priority"]}
    values.update({f"quick_option_{i}": value for i, value in enumerate(draft["options"])})
    values.update({f"quick_answer_{i}": value for i, value in enumerate(draft["answers"])})
    for key, value in values.items():
        key = form_key(key)
        if force or key not in st.session_state:
            st.session_state[key] = value


def change_category():
    save_current_draft()
    st.session_state.quick_active_category = st.session_state[form_key("quick_category")]
    st.session_state.quick_form_epoch += 1
    st.session_state[form_key("quick_category")] = st.session_state.quick_active_category
    restore_draft_widgets(current_draft(), force=True)
    st.session_state.quick_packet = None


def go_to(page):
    st.session_state.simple_workspace = page


def edit_answers():
    st.session_state.quick_view = "setup"


def start_over():
    st.session_state.quick_view = "setup"
    st.session_state.quick_packet = None
    st.session_state.simple_workspace = "RegretLess"


def load_example():
    category = "Buying something"
    draft = {"options": ["Laptop A", "Laptop B"],
             "answers": ["first", "second", "first"], "priority": 1, "is_example": True}
    st.session_state.quick_drafts[category] = draft
    st.session_state.quick_active_category = category
    st.session_state.quick_packet = build_quick_packet(
        category, draft["options"], TEMPLATES[category]["criteria"],
        draft["answers"], draft["priority"], is_example=True)
    st.session_state.quick_view = "results"
    st.session_state.active_analysis = "quick"


def short_name(name):
    name = name.strip() or "Unnamed option"
    return name if len(name) <= 22 else name[:21] + "…"


def setup_page():
    if not st.session_state.quick_form_visible:
        # A fresh widget group avoids reusing empty controls left by the results page.
        st.session_state.quick_form_epoch += 1
        st.session_state.quick_form_visible = True
    st.html('<div class="quick-hero"><div class="eyebrow">REGRETLESS</div>'
            '<h1>Compare two choices.</h1>'
            '<p>Answer three questions to compare what matters to you.</p></div>')
    advanced_ui.restore_widget_value(form_key("quick_category"), st.session_state.quick_active_category)
    category = st.selectbox("What are you deciding?", list(TEMPLATES),
                            key=form_key("quick_category"), on_change=change_category)
    template = TEMPLATES[category]
    draft = current_draft()
    restore_draft_widgets(draft)

    st.markdown("**Your two options**")
    columns = st.columns(2)
    entered_options = [column.text_input(f"Option {i + 1}", key=form_key(f"quick_option_{i}"),
                                 max_chars=60, placeholder=template["options"][i],
                                 on_change=save_current_draft)
                       for i, column in enumerate(columns)]
    # Empty names still use the category defaults in labels and results.
    options = [name.strip() or template["options"][i]
               for i, name in enumerate(entered_options)]
    labels = {"first": short_name(options[0]), "same": "Similar", "second": short_name(options[1])}
    st.markdown("**Which works better for you?**")
    for i, question in enumerate(template["questions"]):
        st.segmented_control(question, ["first", "same", "second"],
                             format_func=lambda answer: labels[answer],
                             key=form_key(f"quick_answer_{i}"), width="stretch",
                             on_change=save_current_draft)
    st.selectbox("What matters most?", [-1, 0, 1, 2], key=form_key("quick_priority"),
                 format_func=lambda i: "Keep it balanced" if i == -1 else template["criteria"][i],
                 on_change=save_current_draft)
    save_current_draft()
    draft = current_draft()
    complete = all(answer is not None for answer in draft["answers"])
    named = all(name.strip() for name in options)
    different = options[0].strip().casefold() != options[1].strip().casefold()
    if named and not different:
        st.warning("Give the two options different names.")
    if not complete:
        st.caption("Pick one answer in each row. You can change your mind later.")
    if st.button("Compare my options", type="primary", width="stretch",
                 disabled=not (complete and named and different)):
        try:
            priority = None if draft["priority"] == -1 else draft["priority"]
            st.session_state.quick_packet = build_quick_packet(
                category, [name.strip() for name in options], template["criteria"],
                list(draft["answers"]), priority, draft["is_example"])
            st.session_state.quick_view = "results"
            st.session_state.active_analysis = "quick"
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    st.button("Try a filled-in example", on_click=load_example, width="stretch")
    st.caption("More options or detailed numbers? Open Advanced model in the sidebar.")


def result_chart(result, options):
    colors = ["#2e6070" if i in result["recommended_indices"] else "#c3ced5" for i in range(2)]
    figure = go.Figure(go.Bar(
        x=result["scores"], y=options, orientation="h", marker_color=colors,
        text=[f"{score:.0f}" for score in result["scores"]], textposition="auto",
        hovertemplate="%{y}: %{x:.1f} points<extra></extra>",
    ))
    figure.update_layout(height=210, margin=dict(l=0, r=15, t=5, b=30),
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         font=dict(color="#203548"), showlegend=False,
                         xaxis=dict(range=[0, 100], title="Priority match · points", fixedrange=True,
                                    gridcolor="#dce4e9", zeroline=False),
                         yaxis=dict(autorange="reversed", automargin=True, fixedrange=True))
    st.plotly_chart(figure, width="stretch", theme=None, config={"displayModeBar": False})


def results_page():
    st.session_state.quick_form_visible = False
    packet = st.session_state.quick_packet
    if packet is None:
        st.session_state.quick_view = "setup"
        st.rerun()
    st.session_state.active_analysis = "quick"
    result, inputs = packet["result"], packet["inputs"]
    options = inputs["strategies"]
    st.caption("YOUR COMPARISON")
    if packet["is_example"]:
        st.info("Example answers only. Change them to compare your own choices.")
    st.title("It's a tie." if result["is_tied"] else f"{result['recommended'][0]} comes out ahead.")
    st.write(result["summary"])
    columns = st.columns(2)
    for column, option, score in zip(columns, options, result["scores"]):
        column.metric(option, f"{score:.0f} / 100", help="Weighted support from your three answers.")
    result_chart(result, options)
    st.caption("A summary of your answers, not a prediction or a measure of real-world differences.")
    first, second = st.columns(2)
    first.button("Edit my answers", on_click=edit_answers, width="stretch")
    second.button("Explore priorities", on_click=go_to, args=("Decision Lab",), width="stretch")

    with st.expander("Why this result?"):
        for criterion, answer, weight in zip(inputs["criteria"], result["answers"], result["normalized_weights"]):
            pick = "Similar" if answer == "same" else options[0 if answer == "first" else 1]
            st.write(f"**{criterion}:** {pick} · {weight:.0%} of this comparison.")
    with st.expander("See the math"):
        st.write("We count your comparisons using a weighted score.")
        for assumption in result["quick_assumptions"]:
            st.caption(assumption)
        st.latex(r"S_i = \sum_{k=1}^{3} w_k s_{ik}")
        rows = []
        for k, criterion in enumerate(inputs["criteria"]):
            rows.append({"Factor": criterion, "Weight": f"{result['normalized_weights'][k]:.1%}",
                         options[0] + " points": result["contributions"][k][0],
                         options[1] + " points": result["contributions"][k][1]})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("For multiple options, measured values, or uncertain future scenarios, use Advanced model.")


def lab_page():
    packet = (st.session_state.quick_packet if st.session_state.active_analysis == "quick"
              else st.session_state.analysis_packet)
    if packet is None:
        st.title("Decision Lab")
        st.write("Make a comparison first, then explore how your priorities change the result.")
        st.button("Start a comparison", on_click=go_to, args=("RegretLess",), type="primary")
        return
    if st.session_state.active_analysis == "quick":
        st.caption("QUICK COMPARISON · Scores count your weighted answers.")
    advanced_ui.lab_page(packet=packet)


st.set_page_config(page_title="RegretLess", page_icon="✦", layout="wide")
# Keep styling separate so the scoring and page flow are easier to inspect.
styles = Path(__file__).with_name("styles.css").read_text(encoding="utf-8")
st.markdown(f"<style>{styles}</style>", unsafe_allow_html=True)
initialize()
with st.sidebar:
    st.markdown("## RegretLess.")
    page = st.radio("Workspace", ["RegretLess", "Decision Lab", "Advanced model"],
                     key="simple_workspace", label_visibility="collapsed")
    st.caption("Your choices. Your priorities.")
if page != "RegretLess":
    st.session_state.quick_form_visible = False
with st.container(key="workspace_panel"):
    if page == "Decision Lab":
        lab_page()
    elif page == "Advanced model":
        st.caption("DETAILED SETUP · Optional tools for mathematical modeling")
        advanced_ui.main_page()
        if st.session_state.analysis_packet is not None:
            st.session_state.active_analysis = "advanced"
    else:
        if st.session_state.quick_view == "results":
            results_page()
        else:
            setup_page()
