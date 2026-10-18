# RegretLess

Compare everyday choices, inspect the calculation, and explore how changing priorities affects a recommendation.

Live app: https://regretless-mathhacks.streamlit.app/

## What it does

The starting page compares two options using three questions and weighted preference scores. Advanced model supports multiple options, factors, and future scenarios. Decision Lab keeps the input scores fixed while changing one factor weight to show how the recommendation responds.

The sample laptop scores are hypothetical, not measured product benchmarks. Scores and recommendations depend on the user's assumptions.

## Run locally

Use Python 3.13 or 3.14. Download and extract this repository, then open a terminal in the extracted folder. Run the following commands in the terminal, not at a Python `>>>` prompt.

### macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

### Windows

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local address printed in the terminal, usually http://localhost:8501/. Keep the terminal open while using the app. Press Control-C to stop the server. The initial dependency installation needs an internet connection. The core comparison workflow makes no external data requests and requires no API key.

## Demo

1. On RegretLess, click **Try a filled-in example**. The weighted preference scores are Laptop A 40 and Laptop B 60; higher is better.
2. In the sidebar, open **Advanced model**, expand **Ready-made modeling demo**, and click **Load laptop demo**. The example calculates automatically.
3. In this separate scenario example, the maximum regrets are A 26 and B 10; lower is better, so B is recommended.
4. Open **Decision Lab** from the sidebar and select **Budget fit**. Budget weights of 40%, 50%, and 60% recommend B, both laptops, and A respectively.

## Mathematics

Factor scores use a defined 0-100 utility scale. Measured values can be converted using fixed zero-point and hundred-point anchors. Relative factor weights are normalized to sum to one.

For option i and scenario j, the weighted utility is:

```text
U[i,j] = sum_k(weight[k] * score[k,i,j])
```

Regret compares options within the same scenario:

```text
R[i,j] = max_a(U[a,j]) - U[i,j]
M[i] = max_j(R[i,j])
```

Minimax Regret retains every option minimizing M. It does not require scenario probabilities and does not assume equal probabilities when they are omitted. If probabilities are supplied, expected utilities are reported separately; they do not replace the Minimax recommendation.

Sensitivity analysis samples one factor weight in 1% steps. Other weights keep their original proportions. The general switch intervals are approximate; the laptop example's crossing at 50% can also be derived analytically.

## Main files

| File | Purpose |
|---|---|
| `app.py` | Quick comparison and navigation |
| `advanced_ui.py` | Detailed inputs, results, and Decision Lab |
| `quick_compare.py` | Three-question scoring rules |
| `decision_engine.py` | Regret calculations and optional expected values |
| `utility_model.py` | Fixed-anchor scoring and weighted utilities |
| `sensitivity.py` | Weight reallocation and repeated analysis |
| `model_validation.py` | Numeric and input-shape checks |
| `cases.py` | Hypothetical laptop case and factor templates |
| `data_sources.py` | Optional data client, unused by the current main interface |
| `styles.css`, `.streamlit/config.toml` | Styling and theme |
| `requirements.txt` | Runtime dependencies |

Python implements the calculations. Streamlit provides the interface, Plotly draws the charts, and pandas handles displayed tables. The deployed version uses Streamlit Community Cloud.

The full project handoff package includes automated tests, local startup helpers, and presentation materials. This repository contains the website runtime and this setup guide.
