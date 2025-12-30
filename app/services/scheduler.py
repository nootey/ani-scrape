import asyncio
import time
from logging import Logger

import pytz
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MAX_INSTANCES, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import config
from app.core.database import DatabaseClient
from app.services.sync import AniListSync
from app.services.tracker import ReleaseTracker


async def run_tracker_job(logger: Logger):
    start = time.time()
    logger.info("Scheduled release check triggered")
    db_client = None

    try:
        # Fresh connection for each check
        db_url = f"sqlite+aiosqlite:///{config.database.path}"
        db_client = DatabaseClient(url=db_url, logger=logger)

        # Sync from AniList first
        sync = AniListSync(logger, db_client)
        await sync.sync_from_anilist()

        # Then check for updates
        tracker = ReleaseTracker(logger, db_client)
        await tracker.check_for_updates()

        elapsed = time.time() - start
        logger.info(f"Release check completed in {elapsed:.2f} seconds")

    except Exception as e:
        logger.error(f"Scheduled release check failed: {e}", exc_info=True)
    finally:
        if db_client:
            await db_client.cleanup()


async def start_scheduler(logger: Logger) -> None:
    s_logger = logger.getChild("scheduler")
    scheduler = AsyncIOScheduler()
    last_job_end_time: float | None = None

    def handle_job_executed(event: JobExecutionEvent):
        job = scheduler.get_job(event.job_id)
        if job and job.next_run_time:
            s_logger.info(f"Next run scheduled at: {job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    def handle_job_error(event: JobExecutionEvent):
        s_logger.error(f"Scheduled job failed: {event.exception}", exc_info=True)

    def handle_max_instances(event: JobExecutionEvent):
        s_logger.warning("Tracker job still running, skipping this interval")

    async def run_tracker_job_with_cooldown(logger: Logger):
        nonlocal last_job_end_time

        # Check if we need to wait for cooldown
        if last_job_end_time is not None:
            time_since_last = time.time() - last_job_end_time
            cooldown_seconds = 60  # 1 minute minimum

            if time_since_last < cooldown_seconds:
                wait_time = cooldown_seconds - time_since_last
                s_logger.info(f"Cooldown active, waiting {wait_time:.1f}s before starting job")
                await asyncio.sleep(wait_time)

        await run_tracker_job(logger)

        last_job_end_time = time.time()

    scheduler.add_listener(handle_job_error, EVENT_JOB_ERROR)
    scheduler.add_listener(handle_job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(handle_max_instances, EVENT_JOB_MAX_INSTANCES)

    timezone = pytz.timezone(config.scheduler.timezone)

    scheduler.add_job(
        run_tracker_job_with_cooldown,
        "interval",
        args=[s_logger],
        hours=config.scheduler.interval_hours,
        timezone=timezone,
        max_instances=1,
    )

    scheduler.start()

    next_run = scheduler.get_jobs()[0].next_run_time
    s_logger.info(f"Scheduler started - next run at: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    try:
        # Keep the scheduler running
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        s_logger.info("Scheduler shutting down gracefully")
        scheduler.shutdown()