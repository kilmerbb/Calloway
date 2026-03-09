"""Worker entry point — runs trigger worker and daily scanner."""
import logging
import time
import threading
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_trigger_loop():
    """Run the trigger worker loop."""
    from app.worker.trigger_worker import run_trigger_worker
    run_trigger_worker()


def run_daily_scan_loop():
    """Run daily scan at each agent's briefing time."""
    from app.worker.daily_scanner import run_daily_scan, send_morning_briefing, _get_all_active_agents

    last_scan_date = None

    while True:
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
                    except Exception as e:
                        logger.error(f"Failed briefing for {agent.name}: {e}")

                last_scan_date = today
            except Exception as e:
                logger.error(f"Daily scan failed: {e}")

        time.sleep(300)  # Check every 5 minutes


if __name__ == "__main__":
    logger.info("Starting worker processes...")

    trigger_thread = threading.Thread(target=run_trigger_loop, daemon=True)
    trigger_thread.start()

    # Run daily scan in main thread
    run_daily_scan_loop()
