"""Streamlit presentation of the governance report.

The page reads reports/governance_report.json. Pass, fail, risk, and release
readiness are taken from that file. This module does not evaluate policy.
"""

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.presentation import (  # noqa: E402
    ANALYSIS_SOURCE,
    POLICY_SOURCE,
    REPORT_SOURCE,
    ReportLoadError,
    condition_rows,
    coverage_panel,
    decision_flow,
    default_report_path,
    gate_label,
    load_governance_report,
    project_fields,
    readiness_label,
    recommended_actions,
    release_explanation,
    risk_explanation,
    risk_label,
    sonar_note,
    sonar_rows,
)

_PAGE_STYLE = """
<style>
    .block-container { padding-top: 1.4rem; max-width: 1080px; }
    div[data-testid="stMetric"] {
        border: 1px solid #d5d8de;
        border-radius: 4px;
        padding: 0.7rem 0.9rem 0.4rem;
        background: #f7f8fa;
    }
    div[data-testid="stMetricLabel"] { color: #3d4450; }
</style>
"""


def main() -> None:
    st.set_page_config(
        page_title="Software Quality Governance Dashboard",
        layout="wide",
    )
    st.markdown(_PAGE_STYLE, unsafe_allow_html=True)
    _render_sidebar()
    try:
        report = load_governance_report(default_report_path())
    except ReportLoadError as error:
        st.title("Software Quality Governance Dashboard")
        st.error(error.message)
        return
    _render_dashboard(report)


def _render_sidebar() -> None:
    st.sidebar.title("Governance Controls")
    st.sidebar.markdown("**Policy Source**")
    st.sidebar.text(POLICY_SOURCE)
    st.sidebar.markdown("**Report Source**")
    st.sidebar.text(REPORT_SOURCE)
    st.sidebar.markdown("**Analysis**")
    st.sidebar.text(ANALYSIS_SOURCE)
    st.sidebar.caption("Refreshing reloads the report from disk. It does not run SonarQube or CI.")
    if st.sidebar.button("Refresh Report"):
        st.rerun()


def _render_dashboard(report: dict) -> None:
    st.title("Software Quality Governance Dashboard")
    st.caption("Automated Software Quality, Risk and Release Readiness")
    st.markdown(
        "This page presents the project governance policy result in the governance report. "
        "It does not replace the SonarQube server-side quality gate."
    )

    gate, readiness, risk = st.columns(3)
    gate.metric("Quality Gate", gate_label(report))
    readiness.metric("Release Readiness", readiness_label(report))
    risk.metric("Risk", risk_label(report))

    st.header("Test Coverage")
    panel = coverage_panel(report)
    coverage, minimum, status = st.columns(3)
    coverage.metric("Coverage", panel["coverage_text"])
    minimum.metric("Policy Minimum", panel["policy_minimum_text"])
    status.metric("Status", panel["status"])
    if panel["statements_text"]:
        st.text(panel["statements_text"])
    if panel["progress"] is not None:
        st.progress(panel["progress"])
    st.markdown(
        f"Coverage condition: **{panel['status']}**\n\n"
        f"Overall release readiness: **{panel['release_readiness']}**"
    )
    st.caption("A passing coverage condition is not a release decision.")

    st.header("SonarQube Evidence")
    st.dataframe(pd.DataFrame(sonar_rows(report)), hide_index=True, width="stretch")
    note = sonar_note(report)
    if note:
        st.info(note)

    st.header("Quality Gate")
    st.caption("Conditions are the project governance policy result, not the SonarQube server gate.")
    rows = condition_rows(report)
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.text("UNAVAILABLE")

    st.header("Release Readiness")
    st.metric("Release Readiness", readiness_label(report))
    st.markdown(release_explanation(report))
    st.caption("A measured policy failure is not the same thing as unavailable evidence.")

    st.header("Risk Assessment")
    st.metric("Risk", risk_label(report))
    st.markdown(risk_explanation(report))

    st.header("Recommended Governance Actions")
    actions = recommended_actions(report)
    if actions:
        for action in actions:
            st.markdown(f"- {action}")
    else:
        st.text("None.")

    st.header("Governance Decision Logic")
    st.caption("One passing metric does not make a release ready.")
    st.code(decision_flow(report), language=None)

    st.header("Project Information")
    project = project_fields(report)
    name, key = st.columns(2)
    name.metric("Project Name", project["name"])
    key.metric("Project Key", project["key"])

    st.header("Report Details")
    with st.expander("View governance report details"):
        st.json(report)


if __name__ == "__main__":
    main()
