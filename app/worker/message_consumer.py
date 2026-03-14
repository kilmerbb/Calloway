"""Redis Streams consumer — processes inbound messages from the calloway:inbound stream.

Reads messages via XREADGROUP, processes them through the pipeline,
ACKs on success, and moves to DLQ after 3 failed attempts.
"""
import json
import logging
import socket
import threading
import time
import uuid

from app.services.redis_pool import get_redis_pool

import redis

logger = logging.getLogger(__name__)

STREAM = "calloway:inbound"
DLQ_STREAM = "calloway:dlq"
GROUP = "calloway-consumers"
CONSUMER_ID = f"worker-{socket.gethostname()}"
MAX_RETRIES = 3
BLOCK_MS = 5000
BATCH_SIZE = 10


def _ensure_consumer_group(r) -> None:
    """Create the consumer group if it doesn't already exist."""
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        logger.info("Created consumer group %s on stream %s", GROUP, STREAM)
    except redis.RedisError as e:
        # BUSYGROUP = group already exists — that's fine
        if "BUSYGROUP" in str(e):
            pass
        else:
            logger.error("Failed to create consumer group: %s", e)
            raise


def _check_duplicate(r, provider_message_id: str) -> bool:
    """Return True if this provider_message_id was already processed (idempotency)."""
    if not provider_message_id:
        return False
    dedup_key = f"calloway:dedup:{provider_message_id}"
    # SET NX with 24h TTL — returns True if key was set (i.e. NOT a duplicate)
    was_set = r.set(dedup_key, "1", nx=True, ex=86400)
    return not was_set  # True means duplicate (key already existed)


def _process_message(entry_id: str, fields: dict) -> None:
    """Route a stream message to the appropriate pipeline handler."""
    correlation_id = fields.get("correlation_id", str(uuid.uuid4()))
    msg_type = fields.get("type", "unknown")
    agent_id = fields.get("agent_id", "")
    payload_raw = fields.get("payload", "{}")

    log_extra = {"correlation_id": correlation_id, "stream_entry": entry_id}

    try:
        payload = json.loads(payload_raw)
    except (json.JSONDecodeError, TypeError):
        logger.error("Invalid JSON payload in stream entry %s", entry_id, extra=log_extra)
        raise ValueError("Malformed payload")

    logger.info(
        "Processing stream message: type=%s agent=%s correlation_id=%s",
        msg_type, agent_id, correlation_id, extra=log_extra,
    )

    if msg_type == "sms":
        from app.api.webhooks import _process_inbound_message_sync
        _process_inbound_message_sync(agent_id, payload)

    elif msg_type == "voice":
        from app.api.webhooks import _process_vapi_transcript_sync
        _process_vapi_transcript_sync(payload)

    elif msg_type == "email":
        from app.api.webhooks import _process_inbound_email_sync
        _process_inbound_email_sync(agent_id, payload)

    else:
        logger.warning("Unknown message type '%s' in stream entry %s", msg_type, entry_id, extra=log_extra)

    logger.info(
        "Successfully processed stream message: type=%s correlation_id=%s",
        msg_type, correlation_id, extra=log_extra,
    )


def _move_to_dlq(r, entry_id: str, fields: dict, error: str) -> None:
    """Move a failed message to the dead-letter queue."""
    dlq_fields = {
        **fields,
        "original_stream": STREAM,
        "original_entry_id": entry_id,
        "error": str(error)[:500],
        "moved_at": str(time.time()),
    }
    try:
        r.xadd(DLQ_STREAM, dlq_fields, maxlen=10000, approximate=True)
        logger.warning("Moved entry %s to DLQ: %s", entry_id, error)
    except redis.RedisError as dlq_err:
        logger.critical("Failed to write to DLQ: %s (original entry: %s)", dlq_err, entry_id)


def run_consumer_loop(shutdown_event: threading.Event) -> None:
    """Main consumer loop — reads from Redis Stream until shutdown."""
    logger.info("Message consumer starting (consumer=%s, group=%s)", CONSUMER_ID, GROUP)

    try:
        r = get_redis_pool()
        _ensure_consumer_group(r)
    except redis.RedisError as e:
        logger.critical("Cannot initialize Redis Streams consumer: %s", e)
        return

    # Track per-entry retry counts in memory
    retry_counts: dict[str, int] = {}

    while not shutdown_event.is_set():
        try:
            # Read new messages assigned to this consumer
            results = r.xreadgroup(
                GROUP, CONSUMER_ID,
                {STREAM: ">"},
                count=BATCH_SIZE,
                block=BLOCK_MS,
            )

            if not results:
                continue

            for stream_name, entries in results:
                for entry_id_raw, fields_raw in entries:
                    # redis-py returns bytes — decode to str
                    entry_id = entry_id_raw.decode() if isinstance(entry_id_raw, bytes) else entry_id_raw
                    fields = {
                        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                        for k, v in fields_raw.items()
                    }

                    correlation_id = fields.get("correlation_id", "unknown")

                    # Idempotency check
                    provider_msg_id = fields.get("provider_message_id", "")
                    if _check_duplicate(r, provider_msg_id):
                        logger.info(
                            "Skipping duplicate message: provider_message_id=%s correlation_id=%s",
                            provider_msg_id, correlation_id,
                        )
                        r.xack(STREAM, GROUP, entry_id)
                        continue

                    try:
                        _process_message(entry_id, fields)
                        r.xack(STREAM, GROUP, entry_id)
                        retry_counts.pop(entry_id, None)

                    except Exception as proc_err:  # Broad catch: worker loop must survive transient errors
                        retries = retry_counts.get(entry_id, 0) + 1
                        retry_counts[entry_id] = retries

                        logger.error(
                            "Processing failed (attempt %d/%d) for entry %s: %s",
                            retries, MAX_RETRIES, entry_id, proc_err,
                            extra={"correlation_id": correlation_id},
                        )

                        if retries >= MAX_RETRIES:
                            _move_to_dlq(r, entry_id, fields, str(proc_err))
                            r.xack(STREAM, GROUP, entry_id)
                            retry_counts.pop(entry_id, None)
                        # else: message stays pending, will be re-read on next claim cycle

        except Exception as loop_err:  # Broad catch: worker loop must survive transient errors
            logger.error("Consumer loop error: %s", loop_err, exc_info=True)
            # Back off before retrying the loop
            shutdown_event.wait(timeout=2)

    logger.info("Message consumer stopped (consumer=%s)", CONSUMER_ID)
