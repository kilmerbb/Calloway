"""Pipeline trace models — captures input/output of every pipeline stage."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ToolCallTrace(BaseModel):
    tool_name: str
    input_json: dict = Field(default_factory=dict)
    output_json: dict = Field(default_factory=dict)
    duration_ms: int = 0
    status: str = "success"  # success / error
    error_message: str | None = None


class StageTrace(BaseModel):
    stage_name: str  # normalizer/resolver/classifier/router/assembler/handler/dispatcher
    started_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    duration_ms: int = 0
    input_summary: dict = Field(default_factory=dict)
    output_summary: dict = Field(default_factory=dict)
    full_input: dict = Field(default_factory=dict)
    full_output: dict = Field(default_factory=dict)
    status: str = "success"  # success / error / skipped
    error_message: str | None = None

    # Handler-specific fields
    model_used: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    system_prompt_hash: str | None = None
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)


class PipelineTrace(BaseModel):
    trace_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow())
    agent_id: UUID
    dry_run: bool = True
    total_duration_ms: int = 0
    stages: list[StageTrace] = Field(default_factory=list)

    # Summary fields (populated after pipeline completes)
    intent_detected: str | None = None
    handler_used: str | None = None
    model_used: str | None = None
    tokens_used: int = 0
    response_text: str | None = None
    outbound_actions: list[dict] = Field(default_factory=list)
