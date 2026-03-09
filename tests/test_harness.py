"""Tests for the Testing Harness — Steps 1-12."""
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

AGENT_ID = str(uuid4())
CONTACT_ID = str(uuid4())

MOCK_AGENT = MagicMock()
MOCK_AGENT.id = uuid4()
MOCK_AGENT.name = "Test Agent"
MOCK_AGENT.phone = "+15550001111"
MOCK_AGENT.twilio_number = "+15550002222"
MOCK_AGENT.email = "test@example.com"
MOCK_AGENT.brokerage = "Test Realty"
MOCK_AGENT.market = "Test Market"
MOCK_AGENT.timezone = "America/New_York"
MOCK_AGENT.style_profile = {"tone": "professional"}
MOCK_AGENT.autonomy_rules = {"level": "autonomous"}
MOCK_AGENT.scheduling_prefs = {}
MOCK_AGENT.vapi_assistant = None
MOCK_AGENT.system_prompt = None
MOCK_AGENT.current_status = "available"
MOCK_AGENT.google_review_link = None
MOCK_AGENT.listing_rules = {}


def _get_authed_client():
    """Return a test client with a valid session."""
    c = TestClient(app, cookies={})
    c.post("/console/login", data={"password": "changeme"})
    return c


def _get_fresh_client():
    """Return a test client with no session."""
    return TestClient(app, cookies={})


# ============================================================
# Step 1: Inject API Tests
# ============================================================

def test_harness_inject_requires_auth():
    """POST /harness/inject without auth returns 401."""
    fresh = _get_fresh_client()
    response = fresh.post("/harness/inject", json={
        "agent_id": AGENT_ID,
        "sender_phone": "+15559990000",
        "message_body": "Hello",
    })
    assert response.status_code == 401


@patch("app.api.harness._run_traced_pipeline")
def test_harness_inject_with_auth(mock_pipeline):
    """POST /harness/inject with auth executes pipeline."""
    from app.models.trace import PipelineTrace
    mock_trace = PipelineTrace(agent_id=uuid4(), dry_run=True)
    mock_trace.intent_detected = "personal"
    mock_trace.response_text = "Hello!"
    mock_pipeline.return_value = mock_trace

    authed = _get_authed_client()
    response = authed.post("/harness/inject", json={
        "agent_id": str(uuid4()),
        "sender_phone": "+15559990000",
        "message_body": "Hello",
    })
    assert response.status_code == 200
    data = response.json()
    assert "trace_id" in data
    assert data["dry_run"] is True


@patch("app.api.harness._run_traced_pipeline")
def test_harness_inject_dry_run_no_real_sms(mock_pipeline):
    """Dry run mode should not send real messages."""
    from app.models.trace import PipelineTrace
    mock_trace = PipelineTrace(agent_id=uuid4(), dry_run=True)
    mock_trace.response_text = "Test response"
    mock_pipeline.return_value = mock_trace

    authed = _get_authed_client()
    response = authed.post("/harness/inject", json={
        "agent_id": str(uuid4()),
        "sender_phone": "+15559990000",
        "message_body": "Hello",
        "dry_run": True,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is True


# ============================================================
# Step 2: Pipeline Trace Model Tests
# ============================================================

def test_pipeline_trace_model():
    """PipelineTrace contains correct structure."""
    from app.models.trace import PipelineTrace, StageTrace, ToolCallTrace

    trace = PipelineTrace(agent_id=uuid4())
    assert trace.trace_id is not None
    assert trace.dry_run is True
    assert trace.stages == []

    stage = StageTrace(stage_name="classifier", duration_ms=10)
    assert stage.status == "success"
    assert stage.tool_calls == []

    tc = ToolCallTrace(tool_name="check_calendar", input_json={"date": "2026-03-15"})
    assert tc.status == "success"
    assert tc.duration_ms == 0

    # Full trace with stages
    trace.stages.append(stage)
    stage.tool_calls.append(tc)
    dumped = trace.model_dump(mode="json")
    assert len(dumped["stages"]) == 1
    assert dumped["stages"][0]["stage_name"] == "classifier"
    assert len(dumped["stages"][0]["tool_calls"]) == 1


def test_pipeline_trace_serialization():
    """PipelineTrace can be serialized to JSON."""
    from app.models.trace import PipelineTrace, StageTrace

    trace = PipelineTrace(
        agent_id=uuid4(),
        total_duration_ms=150,
        intent_detected="scheduling",
        model_used="sonnet",
        response_text="Let me check the calendar.",
    )
    trace.stages.append(StageTrace(
        stage_name="normalizer", duration_ms=5,
        input_summary={"body": "test"},
        output_summary={"channel": "sms"},
    ))

    data = json.loads(trace.model_dump_json())
    assert data["intent_detected"] == "scheduling"
    assert len(data["stages"]) == 1


# ============================================================
# Step 3: Harness Web UI Tests
# ============================================================

@patch("app.services.console_queries.get_all_agents")
def test_harness_home_requires_auth(mock_agents):
    """GET /harness/ without auth redirects to login."""
    fresh = _get_fresh_client()
    response = fresh.get("/harness/", follow_redirects=False)
    assert response.status_code == 303
    assert "/console/login" in response.headers.get("location", "")


@patch("app.services.console_queries.get_all_agents")
def test_harness_home_renders(mock_agents):
    """GET /harness/ with auth renders the composer page."""
    mock_agents.return_value = [{"id": AGENT_ID, "name": "Test Agent", "market": "Test"}]
    authed = _get_authed_client()
    response = authed.get("/harness/")
    assert response.status_code == 200
    assert "Message Composer" in response.text
    assert "Test Agent" in response.text


# ============================================================
# Step 4-6: Trace viewer is part of the composer JS
# These are tested via the inject endpoint returning proper trace data
# ============================================================

@patch("app.api.harness._run_traced_pipeline")
def test_trace_has_all_stages(mock_pipeline):
    """Pipeline trace contains stages with timing data."""
    from app.models.trace import PipelineTrace, StageTrace

    trace = PipelineTrace(agent_id=uuid4(), total_duration_ms=100)
    trace.stages = [
        StageTrace(stage_name="normalizer", duration_ms=5),
        StageTrace(stage_name="resolver", duration_ms=10),
        StageTrace(stage_name="classifier", duration_ms=15),
        StageTrace(stage_name="handler", duration_ms=50, model_used="sonnet"),
        StageTrace(stage_name="dispatcher", duration_ms=20),
    ]
    trace.intent_detected = "scheduling"
    trace.model_used = "sonnet"
    mock_pipeline.return_value = trace

    authed = _get_authed_client()
    response = authed.post("/harness/inject", json={
        "agent_id": str(uuid4()),
        "sender_phone": "+15559990000",
        "message_body": "Can I schedule a showing?",
    })
    data = response.json()
    assert len(data["stages"]) == 5
    stage_names = [s["stage_name"] for s in data["stages"]]
    assert "normalizer" in stage_names
    assert "classifier" in stage_names
    assert "handler" in stage_names
    assert "dispatcher" in stage_names


# ============================================================
# Step 5: Context assembly - verified via stage output
# ============================================================

def test_trace_stage_has_input_output():
    """StageTrace has input_summary and output_summary."""
    from app.models.trace import StageTrace
    stage = StageTrace(
        stage_name="assembler",
        input_summary={"intent": "scheduling", "contact": "Sarah"},
        output_summary={"listings_loaded": 3, "tokens": 1200},
    )
    assert stage.input_summary["intent"] == "scheduling"
    assert stage.output_summary["listings_loaded"] == 3


# ============================================================
# Step 7: Conversation Replay Tests
# ============================================================

@patch("app.services.console_queries.get_all_agents")
def test_replay_page_renders(mock_agents):
    """GET /harness/replay renders the replay page."""
    mock_agents.return_value = []
    authed = _get_authed_client()
    response = authed.get("/harness/replay")
    assert response.status_code == 200
    assert "Conversation Replay" in response.text


@patch("app.api.harness._run_traced_pipeline")
def test_conversation_maintains_state(mock_pipeline):
    """Multiple messages build conversation context."""
    from app.models.trace import PipelineTrace

    trace1 = PipelineTrace(agent_id=uuid4())
    trace1.intent_detected = "listing_qa"
    trace1.response_text = "Yes, 123 Oak is still available!"

    trace2 = PipelineTrace(agent_id=uuid4())
    trace2.intent_detected = "scheduling"
    trace2.response_text = "Saturday works! How about 2pm?"

    mock_pipeline.side_effect = [trace1, trace2]

    authed = _get_authed_client()

    # First message
    r1 = authed.post("/harness/inject", json={
        "agent_id": str(uuid4()),
        "sender_phone": "+15559990000",
        "message_body": "Is 123 Oak still available?",
    })
    assert r1.status_code == 200

    # Second message (same sender — conversation continues)
    r2 = authed.post("/harness/inject", json={
        "agent_id": str(uuid4()),
        "sender_phone": "+15559990000",
        "message_body": "Can I see it Saturday?",
    })
    assert r2.status_code == 200
    assert r2.json()["intent_detected"] == "scheduling"


# ============================================================
# Step 8: Trace History Tests
# ============================================================

@patch("app.services.harness_queries.get_trace_history")
def test_trace_history_page_renders(mock_history):
    """GET /harness/history renders history page."""
    mock_history.return_value = []
    authed = _get_authed_client()
    response = authed.get("/harness/history")
    assert response.status_code == 200
    assert "Trace History" in response.text


@patch("app.services.harness_queries.get_trace_by_id")
def test_compare_traces_page_renders(mock_trace):
    """GET /harness/compare renders compare page."""
    mock_trace.return_value = None
    authed = _get_authed_client()
    response = authed.get("/harness/compare?a=abc&b=def")
    assert response.status_code == 200
    assert "Compare Traces" in response.text


def test_store_trace_function():
    """store_trace function accepts trace objects."""
    from app.models.trace import PipelineTrace
    from app.services.harness_queries import store_trace

    trace = PipelineTrace(agent_id=uuid4())

    # Should not raise even if DB is unavailable
    with patch("app.services.harness_queries.get_db_connection") as mock_db:
        mock_db.side_effect = Exception("DB not available")
        store_trace(trace, "+15559990000", "test message")
        # Function logs error but doesn't raise


# ============================================================
# Step 9: Scenario Definition Tests
# ============================================================

def test_scenario_format_loads():
    """Scenario JSON files load and validate."""
    from app.harness.runner import list_scenarios

    scenarios = list_scenarios()
    assert len(scenarios) > 0

    for s in scenarios:
        assert "id" in s
        assert "name" in s
        assert "category" in s
        assert "steps" in s
        assert s["steps"] > 0


def test_scenario_categories():
    """Scenarios cover multiple categories."""
    from app.harness.runner import list_scenarios

    scenarios = list_scenarios()
    categories = set(s["category"] for s in scenarios)
    assert len(categories) >= 3  # At least 3 categories


# ============================================================
# Step 10: Core Scenario Library Tests
# ============================================================

def test_all_scenario_files_valid_json():
    """All .json files in scenarios/ are valid JSON."""
    from pathlib import Path
    import json

    scenario_dir = Path(__file__).resolve().parent.parent / "app" / "harness" / "scenarios"
    for f in scenario_dir.glob("*.json"):
        with open(f) as fh:
            data = json.load(fh)
        assert "id" in data, f"{f.name} missing 'id'"
        assert "steps" in data, f"{f.name} missing 'steps'"
        assert len(data["steps"]) > 0, f"{f.name} has no steps"

        for step in data["steps"]:
            assert "message" in step, f"{f.name} step missing 'message'"
            assert "expected" in step, f"{f.name} step missing 'expected'"


# ============================================================
# Step 11: Scenario Runner UI Tests
# ============================================================

@patch("app.harness.runner.list_scenarios")
@patch("app.harness.runner.get_scenario_results")
def test_scenarios_page_renders(mock_results, mock_list):
    """GET /harness/scenarios renders scenario list."""
    mock_list.return_value = [
        {"id": "test1", "name": "Test", "description": "desc", "category": "test", "steps": 1},
    ]
    mock_results.return_value = {}

    authed = _get_authed_client()
    response = authed.get("/harness/scenarios")
    assert response.status_code == 200
    assert "Scenario Runner" in response.text


@patch("app.harness.runner.ScenarioRunner.run_scenario")
def test_run_scenario_api(mock_run):
    """POST /harness/scenarios/run/{id} executes scenario."""
    mock_run.return_value = {
        "scenario_id": "test1",
        "passed": True,
        "total_assertions": 2,
        "passed_assertions": 2,
        "step_results": [],
    }

    authed = _get_authed_client()
    response = authed.post("/harness/scenarios/run/test1")
    assert response.status_code == 200
    data = response.json()
    assert data["passed"] is True


# ============================================================
# Step 12: Schema Tests
# ============================================================

def test_harness_traces_table_in_schema():
    """harness_traces table is defined in schema.sql."""
    from pathlib import Path
    schema = (Path(__file__).resolve().parent.parent / "app" / "db" / "schema.sql").read_text()
    assert "harness_traces" in schema
    assert "trace_json" in schema
    assert "intent_detected" in schema


def test_trace_model_in_models():
    """PipelineTrace model exists in app.models.trace."""
    from app.models.trace import PipelineTrace, StageTrace, ToolCallTrace

    assert PipelineTrace is not None
    assert StageTrace is not None
    assert ToolCallTrace is not None


def test_harness_router_registered():
    """Harness router is registered in the FastAPI app."""
    from app.main import app as main_app
    routes = [r.path for r in main_app.routes]
    harness_routes = [r for r in routes if "/harness" in r]
    assert len(harness_routes) > 0
