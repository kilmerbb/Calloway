"""Testing Harness — simulate messages, inspect pipeline, run scenarios."""
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.api.console_auth import check_session
from app.models.trace import PipelineTrace, StageTrace, ToolCallTrace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/harness", tags=["harness"])


def _json_response(data, status_code=200):
    """JSONResponse with str default for non-serializable types."""
    content = json.loads(json.dumps(data, default=str))
    return JSONResponse(content, status_code=status_code)

TEMPLATE_BASE = Path(__file__).resolve().parent.parent / "templates"
TEMPLATE_DIR = TEMPLATE_BASE / "harness"
# Search harness dir first, then console dir (for base.html inheritance)
templates = Jinja2Templates(directory=[str(TEMPLATE_DIR), str(TEMPLATE_BASE / "console")])


def _render(request: Request, template: str, **ctx):
    return templates.TemplateResponse(request, template, ctx)


def _require_auth(request: Request) -> RedirectResponse | None:
    if not check_session(request):
        return RedirectResponse("/console/login", status_code=303)
    return None


# ============================================================
# Inject Request Model
# ============================================================

class InjectRequest(BaseModel):
    agent_id: str
    sender_phone: str
    sender_name: str | None = None
    message_body: str
    channel: str = "sms"
    dry_run: bool = True


# ============================================================
# Pipeline execution with tracing
# ============================================================

def _run_traced_pipeline(req: InjectRequest) -> PipelineTrace:
    """Execute the full pipeline with tracing instrumentation."""
    from app.pipeline.normalizer import normalize_twilio_event
    from app.pipeline.resolver import resolve_contact
    from app.pipeline.classifier import classify_intent
    from app.pipeline.router import route_and_handle
    from app.pipeline.dispatcher import dispatch
    from app.pipeline.consent import check_tcpa_keywords
    from app.pipeline.rate_limiter import check_rate_limits
    from app.services.agent_config import get_agent_by_id

    trace = PipelineTrace(agent_id=UUID(req.agent_id), dry_run=req.dry_run)
    pipeline_start = time.monotonic()

    agent_id = UUID(req.agent_id)
    agent = get_agent_by_id(agent_id)
    if not agent:
        trace.stages.append(StageTrace(
            stage_name="setup",
            status="error",
            error_message=f"Agent {req.agent_id} not found",
        ))
        trace.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
        return trace

    # Stage 1: Normalize
    stage_start = time.monotonic()
    try:
        raw_payload = {
            "From": req.sender_phone,
            "Body": req.message_body,
            "MessageSid": f"harness_{trace.trace_id}",
            "To": agent.twilio_number,
        }
        event = normalize_twilio_event(raw_payload, agent_id)
        stage_ms = int((time.monotonic() - stage_start) * 1000)
        trace.stages.append(StageTrace(
            stage_name="normalizer",
            duration_ms=stage_ms,
            input_summary={"sender": req.sender_phone, "body": req.message_body[:100], "channel": req.channel},
            output_summary={"channel": event.channel, "agent_id": str(event.agent_id)},
            full_input=raw_payload,
            full_output=event.model_dump(mode="json"),
        ))
    except Exception as e:
        trace.stages.append(StageTrace(
            stage_name="normalizer", status="error", error_message=str(e),
            duration_ms=int((time.monotonic() - stage_start) * 1000),
        ))
        trace.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
        return trace

    # Stage 2: Resolve contact
    stage_start = time.monotonic()
    try:
        contact, is_agent_command = resolve_contact(event, agent)
        stage_ms = int((time.monotonic() - stage_start) * 1000)
        trace.stages.append(StageTrace(
            stage_name="resolver",
            duration_ms=stage_ms,
            input_summary={"sender_phone": event.sender_phone},
            output_summary={
                "contact": contact.name if contact else None,
                "is_agent_command": is_agent_command,
                "contact_id": str(contact.id) if contact else None,
                "role": contact.role if contact else None,
                "lifecycle_stage": contact.lifecycle_stage if contact else None,
            },
            full_input={"sender_phone": event.sender_phone, "agent_phone": agent.phone},
            full_output={
                "contact": contact.model_dump(mode="json") if contact else None,
                "is_agent_command": is_agent_command,
            },
        ))
    except Exception as e:
        trace.stages.append(StageTrace(
            stage_name="resolver", status="error", error_message=str(e),
            duration_ms=int((time.monotonic() - stage_start) * 1000),
        ))
        trace.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
        return trace

    # Stage 2A: TCPA check (only for non-agent messages)
    if not is_agent_command:
        stage_start = time.monotonic()
        try:
            tcpa_result = check_tcpa_keywords(event, contact, agent)
            stage_ms = int((time.monotonic() - stage_start) * 1000)
            if tcpa_result:
                trace.stages.append(StageTrace(
                    stage_name="tcpa_check",
                    duration_ms=stage_ms,
                    input_summary={"body": event.body[:50]},
                    output_summary={"action": "blocked", "response": tcpa_result.get("response_text", "")[:80]},
                    full_input={"body": event.body},
                    full_output=tcpa_result,
                ))
                trace.response_text = tcpa_result.get("response_text")
                trace.handler_used = "tcpa"
                trace.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
                return trace
            else:
                trace.stages.append(StageTrace(
                    stage_name="tcpa_check", duration_ms=stage_ms,
                    input_summary={"body": event.body[:50]},
                    output_summary={"action": "passed"},
                    full_input={"body": event.body},
                    full_output={"passed": True},
                ))
        except Exception as e:
            trace.stages.append(StageTrace(
                stage_name="tcpa_check", status="error", error_message=str(e),
                duration_ms=int((time.monotonic() - stage_start) * 1000),
            ))

    # Stage 2B: Rate limiter
    if not is_agent_command:
        stage_start = time.monotonic()
        try:
            rate_result = check_rate_limits(event, contact, agent)
            stage_ms = int((time.monotonic() - stage_start) * 1000)
            if rate_result:
                trace.stages.append(StageTrace(
                    stage_name="rate_limiter",
                    duration_ms=stage_ms,
                    output_summary={"action": "blocked"},
                    full_output=rate_result,
                ))
                trace.handler_used = "rate_limiter"
                trace.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
                return trace
            else:
                trace.stages.append(StageTrace(
                    stage_name="rate_limiter", duration_ms=stage_ms,
                    output_summary={"action": "passed"},
                    full_output={"passed": True},
                ))
        except Exception as e:
            trace.stages.append(StageTrace(
                stage_name="rate_limiter", status="error", error_message=str(e),
                duration_ms=int((time.monotonic() - stage_start) * 1000),
            ))

    # Stage 2C: Consent gate
    if contact and not is_agent_command and contact.consent_status == "revoked":
        trace.stages.append(StageTrace(
            stage_name="consent_gate",
            output_summary={"action": "blocked", "reason": "consent revoked"},
        ))
        trace.handler_used = "consent_gate"
        trace.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
        return trace

    # Stage 3: Classify intent
    stage_start = time.monotonic()
    try:
        intent = classify_intent(event, contact, agent, is_agent_command)
        stage_ms = int((time.monotonic() - stage_start) * 1000)
        trace.stages.append(StageTrace(
            stage_name="classifier",
            duration_ms=stage_ms,
            input_summary={"body": event.body[:100], "sender_type": intent.sender_type},
            output_summary={
                "intent": intent.intent,
                "confidence": intent.confidence,
                "needs_full_context": intent.needs_full_context,
                "language": intent.language_code,
            },
            full_input={"body": event.body, "contact": contact.name if contact else None, "is_agent_command": is_agent_command},
            full_output=intent.model_dump(mode="json"),
        ))
        trace.intent_detected = intent.intent
    except Exception as e:
        trace.stages.append(StageTrace(
            stage_name="classifier", status="error", error_message=str(e),
            duration_ms=int((time.monotonic() - stage_start) * 1000),
        ))
        trace.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
        return trace

    # Stage 3A: Feedback shortcut
    if intent.intent == "feedback":
        trace.handler_used = "feedback"
        trace.stages.append(StageTrace(
            stage_name="handler",
            input_summary={"intent": "feedback"},
            output_summary={"action": "logged feedback score"},
            model_used="template",
        ))
        trace.model_used = "template"
        trace.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
        return trace

    # Stage 4: Route and handle
    stage_start = time.monotonic()
    try:
        decision = route_and_handle(event, contact, intent, agent)
        stage_ms = int((time.monotonic() - stage_start) * 1000)

        # Determine handler from decision context
        handler_name = "unknown"
        if intent.intent == "agent_command":
            handler_name = "agent_command"
        elif intent.intent == "noise":
            handler_name = "noise"
        elif intent.intent == "listing_qa":
            handler_name = "listing_qa"
        elif intent.intent == "escalation":
            handler_name = "escalation"
        elif decision.model_used == "template":
            handler_name = "template"
        elif decision.model_used in ("sonnet", "haiku"):
            handler_name = "full_reasoning"
        trace.handler_used = handler_name

        # Build tool call traces from the decision
        tool_call_traces = []
        for tc in decision.tool_calls:
            tool_call_traces.append(ToolCallTrace(
                tool_name=tc.get("tool_name", "unknown"),
                input_json=tc.get("input", {}),
                output_json=tc.get("output", {}),
            ))

        # System prompt hash for handler stage
        sys_prompt_hash = None
        if decision.model_used not in ("template", None):
            sys_prompt_hash = hashlib.md5(
                f"{agent.name}{agent.style_profile}".encode()
            ).hexdigest()[:8]

        trace.stages.append(StageTrace(
            stage_name="handler",
            duration_ms=stage_ms,
            input_summary={"intent": intent.intent, "contact": contact.name if contact else None},
            output_summary={
                "handler": handler_name,
                "model": decision.model_used,
                "response_length": len(decision.response_text) if decision.response_text else 0,
                "tool_calls": len(decision.tool_calls),
                "triggers_created": len(decision.triggers_to_create),
                "notifications": len(decision.notifications),
            },
            full_input={"intent": intent.model_dump(mode="json"), "event_body": event.body},
            full_output={
                "response_text": decision.response_text,
                "tool_calls": decision.tool_calls,
                "triggers_to_create": decision.triggers_to_create,
                "notifications": decision.notifications,
                "model_used": decision.model_used,
                "tokens_used": decision.tokens_used,
            },
            model_used=decision.model_used,
            tokens_in=decision.tokens_used // 2 if decision.tokens_used else 0,
            tokens_out=decision.tokens_used // 2 if decision.tokens_used else 0,
            system_prompt_hash=sys_prompt_hash,
            tool_calls=tool_call_traces,
        ))

        trace.model_used = decision.model_used
        trace.tokens_used = decision.tokens_used
        trace.response_text = decision.response_text
    except Exception as e:
        trace.stages.append(StageTrace(
            stage_name="handler", status="error", error_message=str(e),
            duration_ms=int((time.monotonic() - stage_start) * 1000),
        ))
        trace.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
        return trace

    # Stage 5: Dispatch
    stage_start = time.monotonic()
    try:
        outbound_actions = []

        if req.dry_run:
            # Capture what would be sent without actually sending
            if decision.response_text:
                if is_agent_command:
                    outbound_actions.append({
                        "type": "sms_to_agent",
                        "to": agent.phone,
                        "body": decision.response_text,
                    })
                elif contact:
                    outbound_actions.append({
                        "type": "sms_to_client",
                        "to": contact.phone,
                        "contact": contact.name,
                        "body": decision.response_text,
                    })

            for notif in decision.notifications:
                outbound_actions.append({"type": "notification", **notif})

            for tc in decision.tool_calls:
                outbound_actions.append({"type": "tool_call", **tc})

            for trigger in decision.triggers_to_create:
                outbound_actions.append({"type": "trigger", **trigger})

            trace.stages.append(StageTrace(
                stage_name="dispatcher",
                duration_ms=int((time.monotonic() - stage_start) * 1000),
                input_summary={"dry_run": True},
                output_summary={"actions_captured": len(outbound_actions)},
                full_output={"dry_run": True, "actions": outbound_actions},
            ))
        else:
            # Actually dispatch
            dispatch(decision, event, contact, agent, is_agent_command)
            outbound_actions.append({"type": "dispatched", "live": True})
            trace.stages.append(StageTrace(
                stage_name="dispatcher",
                duration_ms=int((time.monotonic() - stage_start) * 1000),
                input_summary={"dry_run": False},
                output_summary={"dispatched": True},
                full_output={"dry_run": False, "dispatched": True},
            ))

        trace.outbound_actions = outbound_actions
    except Exception as e:
        trace.stages.append(StageTrace(
            stage_name="dispatcher", status="error", error_message=str(e),
            duration_ms=int((time.monotonic() - stage_start) * 1000),
        ))

    trace.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
    return trace


# ============================================================
# Step 1: Inject API endpoint
# ============================================================

@router.post("/inject")
async def inject_message(request: Request):
    """Simulate an inbound message through the pipeline."""
    if not check_session(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await request.json()
    req = InjectRequest(**body)
    trace = _run_traced_pipeline(req)

    return JSONResponse(trace.model_dump(mode="json"))


# ============================================================
# Step 3: Harness Web Interface — Message Composer
# ============================================================

@router.get("/", response_class=HTMLResponse)
async def harness_home(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import sync_get_all_agents as get_all_agents
    return _render(request, "composer.html",
        page_title="Testing Harness", active_nav="harness",
        agents=get_all_agents(),
    )


@router.get("/agents/{agent_id}/contacts")
async def agent_contacts(request: Request, agent_id: str):
    """Return contacts for an agent (used by message composer dropdown)."""
    if not check_session(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from app.db.connection import get_db_connection
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                """SELECT id, name, phone, role, lifecycle_stage
                   FROM contacts WHERE agent_id = %s ORDER BY name""",
                [agent_id],
            ).fetchall()
        return _json_response([dict(r) for r in (rows or [])])
    except Exception as e:
        return _json_response([])


# ============================================================
# Step 7: Conversation Replay
# ============================================================

@router.get("/replay", response_class=HTMLResponse)
async def replay_page(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import sync_get_all_agents as get_all_agents
    return _render(request, "replay.html",
        page_title="Conversation Replay", active_nav="harness",
        agents=get_all_agents(),
    )


# ============================================================
# Step 8: Trace History + Comparison
# ============================================================

@router.get("/history", response_class=HTMLResponse)
async def trace_history(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.harness_queries import get_trace_history
    agent_filter = request.query_params.get("agent", "")
    intent_filter = request.query_params.get("intent", "")
    model_filter = request.query_params.get("model", "")

    return _render(request, "history.html",
        page_title="Trace History", active_nav="harness",
        traces=get_trace_history(
            agent_id=agent_filter or None,
            intent=intent_filter or None,
            model=model_filter or None,
        ),
        agent_filter=agent_filter,
        intent_filter=intent_filter,
        model_filter=model_filter,
    )


@router.get("/history/{trace_id}", response_class=HTMLResponse)
async def trace_detail(request: Request, trace_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.harness_queries import get_trace_by_id
    trace = get_trace_by_id(trace_id)
    if not trace:
        return RedirectResponse("/harness/history", status_code=303)

    return _render(request, "trace_detail.html",
        page_title="Trace Detail", active_nav="harness",
        trace=trace,
    )


@router.get("/compare", response_class=HTMLResponse)
async def compare_traces(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.harness_queries import get_trace_by_id
    id_a = request.query_params.get("a", "")
    id_b = request.query_params.get("b", "")

    trace_a = get_trace_by_id(id_a) if id_a else None
    trace_b = get_trace_by_id(id_b) if id_b else None

    return _render(request, "compare.html",
        page_title="Compare Traces", active_nav="harness",
        trace_a=trace_a, trace_b=trace_b,
        id_a=id_a, id_b=id_b,
    )


# ============================================================
# Step 8: Store trace after injection
# ============================================================

@router.post("/inject-and-store")
async def inject_and_store(request: Request):
    """Inject a message and store the trace for history."""
    if not check_session(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await request.json()
    req = InjectRequest(**body)
    trace = _run_traced_pipeline(req)

    # Store trace
    from app.services.harness_queries import store_trace
    store_trace(trace, req.sender_phone, req.message_body)

    return JSONResponse(trace.model_dump(mode="json"))


# ============================================================
# Step 11: Scenario Runner Web UI
# ============================================================

@router.get("/scenarios", response_class=HTMLResponse)
async def scenario_list(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.harness.runner import list_scenarios, get_scenario_results
    scenarios = list_scenarios()
    results = get_scenario_results()

    return _render(request, "scenarios.html",
        page_title="Scenarios", active_nav="harness",
        scenarios=scenarios, results=results,
    )


@router.post("/scenarios/run/{scenario_id}")
async def run_scenario(request: Request, scenario_id: str):
    """Run a single scenario."""
    if not check_session(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from app.harness.runner import ScenarioRunner
    runner = ScenarioRunner()
    result = runner.run_scenario(scenario_id)

    return _json_response(result)


@router.post("/scenarios/run-all")
async def run_all_scenarios(request: Request):
    """Run all scenarios."""
    if not check_session(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from app.harness.runner import ScenarioRunner
    runner = ScenarioRunner()
    results = runner.run_all()

    return _json_response(results)


@router.post("/scenarios/run-category/{category}")
async def run_category(request: Request, category: str):
    """Run all scenarios in a category."""
    if not check_session(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from app.harness.runner import ScenarioRunner
    runner = ScenarioRunner()
    results = runner.run_category(category)

    return _json_response(results)


@router.get("/scenarios/{scenario_id}/result", response_class=HTMLResponse)
async def scenario_result(request: Request, scenario_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.harness.runner import get_scenario_result
    result = get_scenario_result(scenario_id)

    return _render(request, "scenario_result.html",
        page_title="Scenario Result", active_nav="harness",
        result=result, scenario_id=scenario_id,
    )
