"""Worker entry point — runs trigger worker and daily scanner."""
import logging
import os
import signal
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Graceful shutdown ────────────────────────────────────────
_shutdown = threading.Event()

HEALTHCHECK_PATH = Path("/tmp/worker-alive")


def _handle_signal(signum, _frame):
    name = signal.Signals(signum).name
    logger.info(f"Received {name} — initiating graceful shutdown")
    _shutdown.set()


def _touch_healthcheck():
    """Update the health-check sentinel so Docker can verify liveness."""
    try:
        HEALTHCHECK_PATH.touch()
    except OSError:
        pass


# ── Worker loops ─────────────────────────────────────────────

def run_trigger_loop():
    """Run the trigger worker loop."""
    from app.worker.trigger_worker import run_trigger_worker_once

    logger.info("Trigger worker started")
    while not _shutdown.is_set():
        try:
            run_trigger_worker_once()
        except Exception as e:  # Broad catch: worker loop must survive transient errors
            logger.error(f"Trigger worker error: {e}")
        _touch_healthcheck()
        # Sleep in small increments so we can respond to shutdown quickly
        _shutdown.wait(timeout=60)
    logger.info("Trigger worker stopped")


def run_daily_scan_loop():
    """Run daily scan at each agent's briefing time."""
    from app.worker.daily_scanner import run_daily_scan, send_morning_briefing, _get_all_active_agents

    last_scan_date = None

    while not _shutdown.is_set():
        now = datetime.now(timezone.utc)
        today = now.date()

        if last_scan_date != today and now.hour >= 7:
            try:
                logger.info("Running daily scan...")
                run_daily_scan()

                agents = _get_all_active_agents()
                for agent in agents:
                    try:
                        send_morning_briefing(agent)
                    except Exception as e:  # Broad catch: worker loop must survive transient errors
                        logger.error(f"Failed briefing for {agent.name}: {e}")

                last_scan_date = today
            except Exception as e:  # Broad catch: worker loop must survive transient errors
                logger.error(f"Daily scan failed: {e}")

        _touch_healthcheck()
        _shutdown.wait(timeout=300)  # Check every 5 minutes

    logger.info("Daily scan loop stopped")


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Set PROCESS_TYPE so pool sizing picks up worker defaults
    os.environ.setdefault("PROCESS_TYPE", "worker")

    logger.info("Starting worker processes...")

    trigger_thread = threading.Thread(target=run_trigger_loop, daemon=True)
    trigger_thread.start()

    # Start the Redis Streams message consumer thread
    from app.worker.message_consumer import run_consumer_loop
    consumer_thread = threading.Thread(target=run_consumer_loop, args=(_shutdown,), daemon=True)
    consumer_thread.start()
    logger.info("Message consumer thread started")

    # Run daily scan in main thread
    run_daily_scan_loop()

    # Wait for background threads to finish their current cycle
    trigger_thread.join(timeout=10)
    consumer_thread.join(timeout=10)
    logger.info("Worker shut down cleanly")
