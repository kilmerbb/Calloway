"""Scenario runner — loads, executes, and validates test scenarios."""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"

# In-memory store for scenario results (last run per scenario)
_scenario_results: dict[str, dict] = {}


def list_scenarios() -> list[dict]:
    """List all available scenario files grouped by category."""
    scenarios = []
    for f in sorted(SCENARIO_DIR.glob("*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
            scenarios.append({
                "id": data.get("id", f.stem),
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "category": data.get("category", "other"),
                "steps": len(data.get("steps", [])),
                "file": f.name,
            })
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load scenario {f.name}: {e}")
    return scenarios


def get_scenario_results() -> dict[str, dict]:
    """Get last run results for all scenarios."""
    return _scenario_results.copy()


def get_scenario_result(scenario_id: str) -> dict | None:
    """Get last run result for a specific scenario."""
    return _scenario_results.get(scenario_id)


def _load_scenario(scenario_id: str) -> dict | None:
    """Load a scenario file by ID."""
    for f in SCENARIO_DIR.glob("*.json"):
        try:
            with open(f) as fh:
                data = json.load(fh)
            if data.get("id") == scenario_id:
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return None


class ScenarioRunner:
    """Execute test scenarios through the harness pipeline."""

    def run_scenario(self, scenario_id: str) -> dict:
        """Run a single scenario and return results."""
        scenario = _load_scenario(scenario_id)
        if not scenario:
            return {"error": f"Scenario {scenario_id} not found", "passed": False}

        result = self._execute_scenario(scenario)
        _scenario_results[scenario_id] = result
        return result

    def run_all(self) -> dict:
        """Run all scenarios and return summary."""
        scenarios = list_scenarios()
        results = []
        for s in scenarios:
            result = self.run_scenario(s["id"])
            results.append(result)

        total = len(results)
        passed = sum(1 for r in results if r.get("passed"))
        total_assertions = sum(r.get("total_assertions", 0) for r in results)
        passed_assertions = sum(r.get("passed_assertions", 0) for r in results)

        return {
            "total_scenarios": total,
            "passed_scenarios": passed,
            "failed_scenarios": total - passed,
            "total_assertions": total_assertions,
            "passed_assertions": passed_assertions,
            "failed_assertions": total_assertions - passed_assertions,
            "results": results,
        }

    def run_category(self, category: str) -> dict:
        """Run all scenarios in a category."""
        scenarios = [s for s in list_scenarios() if s["category"] == category]
        results = []
        for s in scenarios:
            result = self.run_scenario(s["id"])
            results.append(result)

        total = len(results)
        passed = sum(1 for r in results if r.get("passed"))

        return {
            "category": category,
            "total_scenarios": total,
            "passed_scenarios": passed,
            "failed_scenarios": total - passed,
            "results": results,
        }

    def _execute_scenario(self, scenario: dict) -> dict:
        """Execute a scenario and compare expected vs actual."""
        from app.api.harness import _run_traced_pipeline, InjectRequest

        scenario_id = scenario.get("id", "unknown")
        steps = scenario.get("steps", [])
        preconditions = scenario.get("preconditions", {})

        # Set up preconditions
        agent_id = self._setup_preconditions(preconditions)
        if not agent_id:
            return {
                "scenario_id": scenario_id,
                "name": scenario.get("name", ""),
                "passed": False,
                "error": "Failed to set up preconditions — no agent found",
                "step_results": [],
                "total_assertions": 0,
                "passed_assertions": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        step_results = []
        total_assertions = 0
        passed_assertions = 0

        for i, step in enumerate(steps):
            sender = step.get("sender", {})
            sender_phone = sender.get("phone", "+15559990000")

            # Resolve sender identity
            if sender.get("type") == "agent":
                # Use agent's own phone
                from app.services.agent_config import get_agent_by_id
                agent = get_agent_by_id(UUID(agent_id))
                if agent:
                    sender_phone = agent.phone

            req = InjectRequest(
                agent_id=agent_id,
                sender_phone=sender_phone,
                sender_name=sender.get("name"),
                message_body=step.get("message", ""),
                channel=step.get("channel", "sms"),
                dry_run=True,
            )

            trace = _run_traced_pipeline(req)
            expected = step.get("expected", {})

            # Compare expected vs actual
            assertions = []

            if "intent" in expected:
                match = trace.intent_detected == expected["intent"]
                assertions.append({
                    "field": "intent",
                    "expected": expected["intent"],
                    "actual": trace.intent_detected,
                    "passed": match,
                })

            if "handler" in expected:
                match = trace.handler_used == expected["handler"]
                assertions.append({
                    "field": "handler",
                    "expected": expected["handler"],
                    "actual": trace.handler_used,
                    "passed": match,
                })

            if "model_tier" in expected:
                match = trace.model_used == expected["model_tier"]
                assertions.append({
                    "field": "model_tier",
                    "expected": expected["model_tier"],
                    "actual": trace.model_used,
                    "passed": match,
                })

            if "response_contains" in expected:
                for substr in expected["response_contains"]:
                    match = substr.lower() in (trace.response_text or "").lower()
                    assertions.append({
                        "field": "response_contains",
                        "expected": substr,
                        "actual": (trace.response_text or "")[:200],
                        "passed": match,
                    })

            if "response_not_contains" in expected:
                for substr in expected["response_not_contains"]:
                    match = substr.lower() not in (trace.response_text or "").lower()
                    assertions.append({
                        "field": "response_not_contains",
                        "expected": f"NOT '{substr}'",
                        "actual": (trace.response_text or "")[:200],
                        "passed": match,
                    })

            if "tools_called" in expected:
                actual_tools = []
                for stage in trace.stages:
                    if stage.stage_name == "handler":
                        actual_tools = [tc.tool_name for tc in stage.tool_calls]
                        break
                match = actual_tools == expected["tools_called"]
                assertions.append({
                    "field": "tools_called",
                    "expected": expected["tools_called"],
                    "actual": actual_tools,
                    "passed": match,
                })

            if "contact_created" in expected:
                # Check if contact creation happened
                created = any(
                    tc.tool_name == "create_contact"
                    for stage in trace.stages
                    if stage.stage_name == "handler"
                    for tc in stage.tool_calls
                )
                assertions.append({
                    "field": "contact_created",
                    "expected": expected["contact_created"],
                    "actual": created,
                    "passed": created == expected["contact_created"],
                })

            step_passed = all(a["passed"] for a in assertions) if assertions else True
            total_assertions += len(assertions)
            passed_assertions += sum(1 for a in assertions if a["passed"])

            step_results.append({
                "step": i + 1,
                "message": step.get("message", ""),
                "passed": step_passed,
                "assertions": assertions,
                "response_text": trace.response_text,
                "trace_summary": {
                    "intent": trace.intent_detected,
                    "handler": trace.handler_used,
                    "model": trace.model_used,
                    "duration_ms": trace.total_duration_ms,
                },
            })

        all_passed = all(sr["passed"] for sr in step_results) if step_results else True

        return {
            "scenario_id": scenario_id,
            "name": scenario.get("name", ""),
            "category": scenario.get("category", ""),
            "passed": all_passed,
            "step_results": step_results,
            "total_assertions": total_assertions,
            "passed_assertions": passed_assertions,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _setup_preconditions(self, preconditions: dict) -> str | None:
        """Set up scenario preconditions, return agent_id."""
        from app.db.connection import get_db_connection
        import psycopg

        agent_id = preconditions.get("agent_id")
        if agent_id:
            return agent_id

        # Use first available agent
        try:
            with get_db_connection() as conn:
                row = conn.execute(
                    "SELECT id FROM agents ORDER BY created_at LIMIT 1"
                ).fetchone()
            if row:
                return str(row["id"])
        except psycopg.Error as e:
            logger.error(f"Failed to find agent for scenario: {e}")

        return None
