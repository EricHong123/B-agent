# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The analysis contract: SQL allowlist, result schemas and caps, registration, rendering."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from commerce_common.skills import SkillRegistry
from merchant_agent import (
    AnalysisFigure,
    AnalysisResult,
    AnalysisTable,
    MerchantAgentConfig,
    check_analysis_sql,
)
from merchant_agent.analysis import (
    ANALYSIS_TOOL,
    PROGRESS_MESSAGE_MAX_CHARS,
    REPORT_PROGRESS_TOOL,
    SUBMIT_ANALYSIS_TOOL,
    build_analysis_system_prompt,
    build_report_progress_tool,
    cap_analysis_table,
    derive_metrics_payload,
    summarize_result_for_model,
)
from merchant_agent.enrichment import resolve_analysis_metric
from merchant_agent.prompt import build_static_system
from merchant_agent.tools.registry import build_tools
from merchant_agent.types import MerchantSessionState, MetricPoint, MetricSeries

# -- SELECT-only allowlist ----------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT date, sales FROM daily_metrics ORDER BY date",
        "select sum(sales) from daily_metrics",
        "WITH t AS (SELECT * FROM listings) SELECT category, count(*) FROM t GROUP BY 1",
        "SELECT * FROM campaigns;",  # a single trailing semicolon is accepted
    ],
)
def test_allowlist_accepts_read_only_selects(sql):
    assert check_analysis_sql(sql) is None


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "UPDATE listings SET price = 1",
        "DELETE FROM listings",
        "INSERT INTO listings VALUES (1)",
        "DROP TABLE listings",
        "PRAGMA table_info(listings)",
        "ATTACH DATABASE 'x' AS y",
        "SELECT 1; DROP TABLE listings",  # multi-statement
        "SELECT 1 -- with a comment",
        "SELECT /* hidden */ 1",
        "WITH t AS (SELECT 1) DELETE FROM listings",  # write hidden behind a CTE
        "VACUUM",
        "CREATE TABLE t (x)",
        "SELECT * FROM pragma_table_info('listings')",
        "SELECT load_extension('x')",
        "SELECT readfile('/etc/passwd')",
    ],
)
def test_allowlist_rejects_everything_that_is_not_one_select(sql):
    assert check_analysis_sql(sql) is not None


# -- report_progress contract ---------------------------------------------------------


def test_report_progress_tool_schema():
    tool = build_report_progress_tool()
    assert tool["name"] == REPORT_PROGRESS_TOOL
    schema = tool["input_schema"]
    assert schema["required"] == ["message"]
    assert schema["additionalProperties"] is False
    message = schema["properties"]["message"]
    assert message["type"] == "string"
    assert message["maxLength"] == PROGRESS_MESSAGE_MAX_CHARS == 140


def test_analysis_prompt_carries_the_progress_and_submit_rule():
    prompt = build_analysis_system_prompt(MerchantAgentConfig(brand_name="ACME"))
    assert REPORT_PROGRESS_TOOL in prompt
    assert SUBMIT_ANALYSIS_TOOL in prompt


# -- table caps -----------------------------------------------------------------------


def test_cap_analysis_table_enforces_row_and_byte_caps():
    config = MerchantAgentConfig(max_analysis_rows=3, max_analysis_table_chars=500)
    table = AnalysisTable(columns=["a"], rows=[[i] for i in range(10)], row_count=10)
    capped = cap_analysis_table(table, config)
    assert len(capped.rows) == 3
    assert capped.truncated

    wide = AnalysisTable(columns=["blob"], rows=[["x" * 400], ["y" * 400]], row_count=2)
    capped = cap_analysis_table(wide, config)
    assert len(capped.rows) == 1
    assert capped.truncated


# -- result schema ---------------------------------------------------------------------


def test_analysis_result_clips_its_lists_instead_of_rejecting():
    result = AnalysisResult(
        question="q",
        headline="h",
        findings=[f"finding {i}" for i in range(9)],
        figures=[AnalysisFigure(label=f"fig {i}", value=float(i)) for i in range(9)],
        caveats=[f"caveat {i}" for i in range(5)],
        derived_series=[MetricSeries(metric=f"m{i}") for i in range(5)],
    )
    assert [line.split()[-1] for line in result.findings] == [str(i) for i in range(8)]
    assert [figure.value for figure in result.figures] == [float(i) for i in range(8)]
    assert [line.split()[-1] for line in result.caveats] == [str(i) for i in range(4)]
    assert [series.metric for series in result.derived_series] == ["m0", "m1", "m2", "m3"]


def test_analysis_result_truncates_its_text_fields_instead_of_rejecting():
    result = AnalysisResult(
        question="q" * 400, headline="h" * 300, method_note="m" * 400, findings=["x" * 450]
    )
    assert len(result.question) == 300 and result.question.endswith("…")
    assert len(result.headline) == 200 and result.headline.endswith("…")
    assert len(result.method_note) == 300 and result.method_note.endswith("…")
    assert len(result.findings[0]) == 300 and result.findings[0].endswith("…")


def test_analysis_result_downsamples_oversize_series():
    points = [MetricPoint(date=f"2026-01-{i % 28 + 1:02d}", value=float(i)) for i in range(120)]
    result = AnalysisResult(
        question="q",
        headline="h",
        derived_series=[MetricSeries(metric="sales", points=points)],
    )
    kept = result.derived_series[0].points
    assert len(kept) == 40
    assert kept[0].value == 0.0 and kept[-1].value == 119.0


def test_analysis_figure_truncates_its_text_fields_instead_of_rejecting():
    figure = AnalysisFigure(label="l" * 200, value=1.0, unit="u" * 40, note="n" * 300)
    assert len(figure.label) == 80 and figure.label.endswith("…")
    assert len(figure.unit) == 16 and figure.unit.endswith("…")
    assert len(figure.note) == 140 and figure.note.endswith("…")


def test_analysis_figure_rejects_a_non_numeric_value():
    with pytest.raises(ValidationError):
        AnalysisFigure(label="share of drop", value="quite a lot")


def test_in_bounds_analysis_result_passes_through_unchanged():
    result = _result()
    assert result.question == "why did kids-room sales drop"
    assert result.headline == "Kids-room drove 78% of the week's sales drop"
    assert result.findings == ["kids-room fell 21% while all other categories were flat"]
    assert [figure.label for figure in result.figures] == [
        "kids-room share of drop",
        "kids-room sales change",
    ]
    assert [figure.unit for figure in result.figures] == ["%", "%"]
    assert len(result.derived_series[0].points) == 2
    assert result.caveats == ["one week of data"]
    assert result.method_note is None  # the optional text fields accept None


# -- config-gated registration ---------------------------------------------------------


def test_run_analysis_registers_only_when_enabled():
    skills: list[str] = []
    default_tools = build_tools(MerchantAgentConfig(), skills)
    enabled_tools = build_tools(MerchantAgentConfig(enable_analysis=True), skills)
    default_names = [tool.get("name") for tool in default_tools]
    enabled_names = [tool.get("name") for tool in enabled_tools]
    assert ANALYSIS_TOOL not in default_names
    assert enabled_names == default_names + [ANALYSIS_TOOL]
    assert json.dumps(default_tools, sort_keys=True) == json.dumps(
        build_tools(MerchantAgentConfig(), skills), sort_keys=True
    )


def test_prompt_rule_is_config_gated():
    skills = SkillRegistry([])
    default_prompt = build_static_system(MerchantAgentConfig(), skills)
    enabled_prompt = build_static_system(MerchantAgentConfig(enable_analysis=True), skills)
    assert ANALYSIS_TOOL not in default_prompt
    assert ANALYSIS_TOOL in enabled_prompt
    assert default_prompt == build_static_system(MerchantAgentConfig(), skills)


# -- provenance and rendering ------------------------------------------------------------


def _result() -> AnalysisResult:
    return AnalysisResult(
        question="why did kids-room sales drop",
        headline="Kids-room drove 78% of the week's sales drop",
        findings=["kids-room fell 21% while all other categories were flat"],
        figures=[
            AnalysisFigure(label="kids-room share of drop", value=78.0, unit="%"),
            AnalysisFigure(label="kids-room sales change", value=-21.0, unit="%"),
        ],
        derived_series=[
            MetricSeries(
                metric="kids_room_share",
                granularity="day",
                period="2026-06-19/2026-06-25",
                points=[
                    MetricPoint(date="2026-06-24", value=11.2),
                    MetricPoint(date="2026-06-25", value=9.1),
                ],
            )
        ],
        caveats=["one week of data"],
    )


def test_remember_analysis_assigns_server_side_ids():
    state = MerchantSessionState()
    first = state.remember_analysis(_result())
    second = state.remember_analysis(_result())
    assert (first, second) == ("AN-1", "AN-2")
    assert state.seen_analyses["AN-1"].analysis_id == "AN-1"


def test_derive_metrics_payload_renders_from_the_record():
    result = _result()
    MerchantSessionState().remember_analysis(result)
    payload = derive_metrics_payload(result)
    assert payload["title"].startswith("Kids-room drove")
    tiles = [entry for entry in payload["metrics"] if "value" in entry]
    assert {tile["metric"] for tile in tiles} == {
        "kids-room share of drop",
        "kids-room sales change",
    }
    assert tiles[0]["value"] == 78.0
    series_entries = [entry for entry in payload["metrics"] if "series" in entry]
    assert len(series_entries) == 1
    assert series_entries[0]["series"]["points"][0]["value"] == 11.2
    assert payload["period"] == "2026-06-19/2026-06-25"


def test_summary_for_model_omits_bulk_series_points():
    result = _result()
    summary = summarize_result_for_model(result)
    assert summary["derived_series"] == [
        {
            "metric": "kids_room_share",
            "points": 2,
            "period": "2026-06-19/2026-06-25",
            "segment": None,
        }
    ]
    assert "11.2" not in json.dumps(summary)


def test_present_metrics_resolves_analysis_figures():
    state = MerchantSessionState()
    state.remember_analysis(_result())
    resolved = resolve_analysis_metric(state, "AN-1 kids-room share of drop")
    assert resolved == {
        "metric": "kids-room share of drop",
        "value": 78.0,
        "change_pct": None,
        "currency": None,
    }
    series = resolve_analysis_metric(state, "kids_room_share trend")
    assert series is not None and series["series"]["metric"] == "kids_room_share"
    assert resolve_analysis_metric(state, "a metric no analysis produced") is None


def test_forbidden_sql_blocks_select_into_variants():

    assert check_analysis_sql("SELECT * INTO new_table FROM listings") is not None
    assert check_analysis_sql("SELECT title FROM listings INTO OUTFILE '/tmp/x'") is not None
    assert check_analysis_sql("SELECT title, stock FROM listings WHERE stock < 5") is None
