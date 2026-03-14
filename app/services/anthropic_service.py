"""Claude API wrapper with model tiering, caching, retry, and token counting."""
import asyncio
import json
import logging
import time
from uuid import UUID

import anthropic

from app.config import get_settings
from app.models.schemas import AgentDecision

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-5-20241022"

# Cost per 1M tokens (input/output) in cents
MODEL_COSTS = {
    HAIKU_MODEL: {"input": 100, "output": 500},       # $1/$5 per 1M
    SONNET_MODEL: {"input": 300, "output": 1500},      # $3/$15 per 1M
}


class AnthropicClient:
    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)

    def _track_usage(self, agent_id: UUID, model: str, input_tokens: int, output_tokens: int):
        """Persist token usage to the usage_metrics table (C-2 fix).

        Previously tracked in an in-memory dict that was lost on restart.
        Now writes directly to the DB, which is the single source of truth.
        """
        from app.db.connection import get_db_connection

        costs = MODEL_COSTS.get(model, MODEL_COSTS[HAIKU_MODEL])
        cost_cents = int(
            (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000
        )
        total_tokens = input_tokens + output_tokens

        try:
            with get_db_connection() as conn:
                conn.execute(
                    """INSERT INTO usage_metrics (agent_id, date, llm_calls, llm_tokens_used, llm_cost_cents)
                       VALUES (%s, CURRENT_DATE, 1, %s, %s)
                       ON CONFLICT (agent_id, date)
                       DO UPDATE SET llm_calls = usage_metrics.llm_calls + 1,
                                     llm_tokens_used = usage_metrics.llm_tokens_used + %s,
                                     llm_cost_cents = usage_metrics.llm_cost_cents + %s""",
                    [str(agent_id), total_tokens, cost_cents, total_tokens, cost_cents],
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to persist token usage: {e}")

    def get_usage(self, agent_id: UUID) -> dict:
        """Get token usage for an agent from the database."""
        from app.db.connection import get_db_connection

        try:
            with get_db_connection() as conn:
                row = conn.execute(
                    """SELECT date, llm_tokens_used as tokens, llm_cost_cents as cost_cents
                       FROM usage_metrics
                       WHERE agent_id = %s AND date = CURRENT_DATE""",
                    [str(agent_id)],
                ).fetchone()
            if row:
                return {str(row["date"]): {"tokens": row["tokens"], "cost_cents": row["cost_cents"]}}
        except Exception as e:
            logger.error(f"Failed to read token usage: {e}")
        return {}

    def _call_with_retry(self, func, max_retries=1):
        """Call a function with retry on rate limit."""
        for attempt in range(max_retries + 1):
            try:
                start = time.time()
                result = func()
                latency = int((time.time() - start) * 1000)
                return result, latency
            except anthropic.RateLimitError:
                if attempt < max_retries:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"Rate limited, retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise
            except anthropic.APIError as e:
                logger.error(f"Anthropic API error: {e}")
                raise

    def classify(
        self,
        system_prompt: str,
        message: str,
        agent_id: UUID,
        max_tokens: int = 200,
    ) -> dict:
        """
        Use Claude Haiku for intent classification. Cheap and fast.
        Returns parsed JSON.
        """
        def _call():
            return self.client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=max_tokens,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": message}],
            )

        response, latency = self._call_with_retry(_call)

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        self._track_usage(agent_id, HAIKU_MODEL, input_tokens, output_tokens)

        # Parse JSON from response
        text = response.content[0].text
        try:
            # Try to extract JSON from the response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            result = json.loads(text.strip())
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse classify response as JSON: {text[:100]}")
            result = {"raw_response": text}

        result["_tokens"] = input_tokens + output_tokens
        result["_latency_ms"] = latency
        return result

    def reason(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        agent_id: UUID,
        tool_executor=None,
        max_tokens: int = 1000,
        max_rounds: int = 3,
    ) -> AgentDecision:
        """
        Use Claude Sonnet for complex reasoning with tools.
        Handles tool_use responses and iterates up to max_rounds.
        """
        total_input = 0
        total_output = 0
        all_tool_calls = []
        current_messages = list(messages)

        for round_num in range(max_rounds):
            def _call():
                return self.client.messages.create(
                    model=SONNET_MODEL,
                    max_tokens=max_tokens,
                    system=[{
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }],
                    messages=current_messages,
                    tools=tools if tools else None,
                )

            response, latency = self._call_with_retry(_call)
            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens

            # Check if response contains tool use
            has_tool_use = any(
                block.type == "tool_use" for block in response.content
            )

            if not has_tool_use or tool_executor is None:
                # Final text response
                text_blocks = [
                    block.text for block in response.content
                    if block.type == "text"
                ]
                response_text = "\n".join(text_blocks) if text_blocks else None

                self._track_usage(agent_id, SONNET_MODEL, total_input, total_output)

                return AgentDecision(
                    response_text=response_text,
                    tool_calls=all_tool_calls,
                    model_used="sonnet",
                    tokens_used=total_input + total_output,
                )

            # Process tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_call = {
                        "tool_name": block.name,
                        "input": block.input,
                        "id": block.id,
                    }
                    all_tool_calls.append(tool_call)

                    try:
                        result = tool_executor(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result) if not isinstance(result, str) else result,
                        })
                    except Exception as e:
                        logger.error(f"Tool {block.name} failed: {e}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps({"error": str(e)}),
                            "is_error": True,
                        })

            # Add assistant response and tool results for next round
            current_messages.append({"role": "assistant", "content": response.content})
            current_messages.append({"role": "user", "content": tool_results})

        # Exhausted rounds — return what we have
        self._track_usage(agent_id, SONNET_MODEL, total_input, total_output)
        return AgentDecision(
            response_text="I need a moment to process this. Let me get back to you.",
            tool_calls=all_tool_calls,
            model_used="sonnet",
            tokens_used=total_input + total_output,
        )

    def compose(
        self,
        system_prompt: str,
        context: str,
        instruction: str,
        agent_id: UUID,
        max_tokens: int = 500,
        model: str | None = None,
    ) -> str:
        """
        Use Claude for message composition. Returns just the text response.
        Can use either Haiku or Sonnet based on the model parameter.
        """
        use_model = model or HAIKU_MODEL

        def _call():
            return self.client.messages.create(
                model=use_model,
                max_tokens=max_tokens,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{
                    "role": "user",
                    "content": f"{context}\n\n{instruction}",
                }],
            )

        response, latency = self._call_with_retry(_call)

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        self._track_usage(agent_id, use_model, input_tokens, output_tokens)

        return response.content[0].text


# Singleton instance
_client: AnthropicClient | None = None


def get_anthropic_client() -> AnthropicClient:
    global _client
    if _client is None:
        _client = AnthropicClient()
    return _client
