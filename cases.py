"""Example scores and decision templates."""

LAPTOP_CASE = {
    "title": "Laptop Purchase",
    "strategies": ["Laptop A", "Laptop B"],
    "scenarios": ["Everyday use", "Heavy workload"],
    "criteria": ["Budget fit", "Performance fit"],
    "criterion_matrices": [
        [[90, 90], [50, 50]],
        [[70, 30], [80, 100]],
    ],
    "assumption_notice": "All scores, scenarios, and weights are hypothetical assumptions for demonstration, not measured product benchmarks.",
    "score_anchors": {
        "0": "Does not meet the user's defined minimum acceptable fit.",
        "50": "Moderately meets the user's stated requirements.",
        "100": "Fully meets the user's defined target.",
        "intermediate": "Use fixed anchors and a documented rule; do not rescale when alternatives change.",
    },
    "score_meaning": {"0": "Fails the defined minimum acceptable fit", "50": "Partially meets the user's stated target", "100": "Fully meets the stated target"},
    "criterion_guidance": {
        "Budget fit": "Score against the user's fixed budget and price/value target. 100 means comfortably within the target; 50 means a meaningful trade-off; 0 means outside the user's acceptable range.",
        "Performance fit": "Score against a written workload requirement (for example, ability to handle everyday tasks versus demanding applications). 100 means the target workload is fully supported; 50 means some compromise; 0 means it cannot meet the minimum requirement.",
    },
    "double_counting_check": "Budget fit means affordability/value relative to the user's budget; do not add a second criterion that scores the same price effect. Performance fit concerns workload capability only.",
}

# General templates provide factor definitions, not product data.
CASE_TEMPLATES = {
    "purchase": {
        "title": "Purchase Decision",
        "criteria": ["Budget fit", "Reliability fit", "Feature fit"],
        "anchors": {0: "Fails minimum requirement", 50: "Partially meets requirement", 100: "Fully meets requirement"},
        "criterion_guidance": {"Budget fit": "Compare total price with the user's pre-set budget bands.", "Reliability fit": "Use a stated warranty/reliability standard and disclosed evidence; do not invent reliability data.", "Feature fit": "Count only features the user explicitly needs, against a fixed checklist."},
        "double_counting_check": "Do not score price again under value if Budget fit already captures the same price preference.",
    },
    "travel": {
        "title": "Travel Choice",
        "criteria": ["Total cost fit", "Travel-time fit", "Accessibility fit"],
        "anchors": {0: "Unacceptable against the user's fixed standard", 50: "Acceptable with trade-offs", 100: "Meets the target standard"},
        "criterion_guidance": {"Total cost fit": "Compare the full expected fare and required fees with a fixed budget band.", "Travel-time fit": "Score door-to-door duration against a user-defined maximum; keep the time unit consistent.", "Accessibility fit": "Use a checklist of required mobility/accessibility needs, not assumptions about the traveler."},
        "double_counting_check": "Keep travel time separate from cost; do not count the same fare or delay penalty in multiple criteria.",
    },
    "study_work": {
        "title": "Study and Work Plan",
        "criteria": ["Deadline fit", "Focus fit", "Workload sustainability"],
        "anchors": {0: "Cannot meet the minimum standard", 50: "Meets part of the standard", 100: "Meets the target standard"},
        "criterion_guidance": {"Deadline fit": "Score against a fixed deadline and the estimated time needed for required tasks.", "Focus fit": "Score how well the plan matches the user's chosen uninterrupted-work conditions.", "Workload sustainability": "Score whether the plan leaves realistic breaks and recovery time against a defined standard."},
        "double_counting_check": "Avoid scoring hours available under both Deadline fit and Workload sustainability unless the definitions are distinct.",
    },
    "event": {
        "title": "Event Plan",
        "criteria": ["Budget fit", "Participation fit", "Accessibility fit"],
        "anchors": {0: "Fails the stated minimum", 50: "Partly meets the target", 100: "Fully meets the target"},
        "criterion_guidance": {"Budget fit": "Compare total venue, supplies, and operating costs against the fixed budget.", "Participation fit": "Score against explicit activity goals and the number of participants the plan can meaningfully engage.", "Accessibility fit": "Use a checklist of venue access, sensory needs, and participation barriers defined by organizers."},
        "double_counting_check": "Do not count attendance and participation as separate criteria if both are proxies for the same outcome.",
    },
    "resource_allocation": {
        "title": "Resource Allocation",
        "criteria": ["Need coverage", "People served", "Implementation feasibility"],
        "anchors": {0: "No meaningful coverage/feasibility", 50: "Partial coverage/feasibility", 100: "Meets the defined target"},
        "criterion_guidance": {"Need coverage": "Score how closely allocation addresses a documented priority-need checklist.", "People served": "Score the number of unique beneficiaries against a stated target; do not count repeat contacts as unique people.", "Implementation feasibility": "Score against staff, time, access, and operational constraints confirmed by the organization."},
        "double_counting_check": "If Need coverage already includes number of people served, define the two measures so they do not duplicate beneficiaries.",
    },
    "custom": {
        "title": "Custom Decision",
        "criteria": [],
        "anchors": {0: "User-defined unacceptable fit", 50: "User-defined middle anchor", 100: "User-defined target fit"},
        "criterion_guidance": {"User-defined criterion": "For every added factor, define what evidence earns 0, 50, and 100 before scoring any option. Use intermediate scores only under a consistent rule."},
        "double_counting_check": "Write a one-sentence definition for each criterion and check whether changing one underlying fact changes more than one score.",
    },
}


def get_case_template(case_type):
    """Return a copy so UI edits cannot mutate shared template data."""
    from copy import deepcopy
    if case_type == "laptop":
        return deepcopy(LAPTOP_CASE)
    if case_type not in CASE_TEMPLATES:
        raise ValueError("Unknown case template.")
    return deepcopy(CASE_TEMPLATES[case_type])
