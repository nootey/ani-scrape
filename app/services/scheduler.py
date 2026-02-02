import asyncio
import time
from logging import Logger

import pytz
from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MAX_INSTANCES,
    JobExecutionEvent,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import config
from app.core.database import DatabaseClient
from app.services.sync import AniListSync
from app.services.tracker import ReleaseTracker

async def run_scrape_job(logger: Logger, retry_count: int = 0):
    start = time.time()
    max_retries = 3
    retry_delay = 60  # seconds

    logger.info(f"Scheduled scrape triggered (attempt {retry_count + 1}/{max_retries + 1})")
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
        elapsed = time.time() - start
        error_msg = f"Scheduled scrape failed after {elapsed:.2f}s: {str(e)}"
        logger.error(error_msg, exc_info=True)

        if retry_count < max_retries:
            logger.warning(f"Retrying in {retry_delay}s...")
            await asyncio.sleep(retry_delay)
            return await run_scrape_job(logger, retry_count + 1)
        else:
            logger.error("Max retries reached, giving up")
            return False

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
            s_logger.info(
                f"Next run scheduled at: {job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )

    def handle_job_error(event: JobExecutionEvent):
        s_logger.error(f"Scheduled job failed: {event.exception}", exc_info=True)

    def handle_max_instances(event: JobExecutionEvent):
        s_logger.warning("Tracker job still running, skipping this interval")

    async def run_scrape_job_with_cooldown(logger: Logger):
        nonlocal last_job_end_time

        job_start = time.time()
        s_logger.info(f"Job starting at {time.strftime('%H:%M:%S')}")

        # Cooldown check
        if last_job_end_time is not None:
            time_since_last = time.time() - last_job_end_time
            cooldown_seconds = 60

            if time_since_last < cooldown_seconds:
                wait_time = cooldown_seconds - time_since_last
                s_logger.info(f"Cooldown active, waiting {wait_time:.1f}s before starting job")
                await asyncio.sleep(wait_time)

        # Create task with cancellation
        timeout_seconds = (config.scheduler.interval_minutes * 60) - 30  # 30s buffer
        scrape_task = asyncio.create_task(run_scrape_job(logger))

        try:
            await asyncio.wait_for(scrape_task, timeout=timeout_seconds)
            s_logger.info("Scrape completed successfully")
        except asyncio.TimeoutError:
            error_msg = f"Scrape exceeded timeout of {timeout_seconds}s - CANCELLING TASK"
            s_logger.error(error_msg)
            scrape_task.cancel()

            try:
                # Wait for cancellation to propagate
                await asyncio.wait_for(scrape_task, timeout=10)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                s_logger.warning("Task cancelled or force-stopped after timeout")

        # Calculate and log duration
        job_duration = time.time() - job_start
        s_logger.info(f"Job completed in {job_duration:.1f}s")

        # Warn if approaching interval limit
        interval_seconds = config.scheduler.interval_minutes * 60
        if job_duration > (interval_seconds * 0.8):
            warning = f"⚠️ Scrape took {job_duration:.1f}s ({job_duration / 60:.1f}min), close to {interval_seconds}s interval."
            s_logger.warning(warning)

        last_job_end_time = time.time()

    scheduler.add_listener(handle_job_error, EVENT_JOB_ERROR)
    scheduler.add_listener(handle_job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(handle_max_instances, EVENT_JOB_MAX_INSTANCES)

    timezone = pytz.timezone(config.scheduler.timezone)

    scheduler.add_job(
        run_scrape_job_with_cooldown,
        "interval",
        args=[s_logger],
        hours=config.scheduler.interval_hours,
        timezone=timezone,
        max_instances=1,
    )

    scheduler.start()

    next_run = scheduler.get_jobs()[0].next_run_time
    s_logger.info(
        f"Scheduler started - next run at: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    )

    try:
        # Keep the scheduler running
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        s_logger.info("Scheduler shutting down gracefully")
        scheduler.shutdown()
    except Exception as e:
        s_logger.error(f"Scheduler crashed: {e}", exc_info=True)
        raise