"""Ask the platform to run the nightly preparation pass.

The prefetch handler has been registered with the job dispatcher all along, and
`prefetch_scripture_summaries()` does the work correctly — but nothing anywhere ever queued
it. Recurring work on this platform needs a `schedules` row linked to a `job_type`; this app
had no seed migration, no lifecycle hook, and declared no job types, and the platform never
referenced `scripture_prefetch` outside the handler registration itself. So the pass
documented as nightly had never run on any install: chapters were only ever prepared when
somebody opened them.

`ensure_schedule()` is idempotent and safe to call on every boot — it upserts against a
stable id and reconciles rather than re-creating, so it does not drift the fire time.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SCHEDULE_ID = "sch-scripture-prefetch-nightly"
JOB_TYPE = "scripture_prefetch"

# 03:00, deliberately clear of the 02:00 backup: both are heavy, and the preparation pass
# makes a model call per missing item per chapter. Fixed rather than configurable — there is
# no setting anybody has asked to change, and an hour that only matters while the household
# is asleep is not worth a knob.
TIME_OF_DAY = "03:00"


def ensure_schedule() -> None:
    """Create or reconcile the nightly preparation schedule. Never raises.

    Always active. A household with no bookmarks is not a reason to switch the schedule off:
    bookmarks come and go, the pass already answers "no bookmarks found — nothing to
    prefetch" in that case, and a schedule that disables itself is a second thing to debug
    when preparation stops happening.
    """
    try:
        from apps.schedules import data as _sched

        existing = None
        try:
            existing = _sched.get_schedule(SCHEDULE_ID)
        except Exception:
            # Missing table / early boot — treat as "not yet created". Never fatal.
            logger.debug("SCRIPTURES: get_schedule(%s) failed — treating as new", SCHEDULE_ID,
                         exc_info=True)

        # Reset the countdown only on first creation, re-activation, or a time change, so a
        # plain reconcile on every boot does not push tonight's run later each time.
        reset = (
            existing is None
            or not existing.get("active")
            or existing.get("time_of_day") != TIME_OF_DAY
        )
        next_due = _sched.compute_next_due("daily", {"every": 1}, TIME_OF_DAY) if reset else None

        _sched.upsert_schedule(
            SCHEDULE_ID,
            title="Nightly Scripture Preparation",
            description=(
                "Generates the missing summary, people, places and pronouns for every "
                "bookmarked chapter and the chapters ahead of it, so a reader opens them "
                "with the study material already there. Handler: "
                "prefetch.py:prefetch_scripture_summaries."
            ),
            category="general",
            created_by="system",
            recurrence_type="daily",
            recurrence_rule={"every": 1},
            time_of_day=TIME_OF_DAY,
            linked_entity_id=JOB_TYPE,
            linked_entity_type="job",
            next_due=next_due,
            active=True,
            reminder_mins=0,
            notify_channel="none",
        )
        logger.info("SCRIPTURES: nightly preparation scheduled for %s", TIME_OF_DAY)
    except Exception:
        logger.warning("SCRIPTURES: could not schedule the nightly preparation pass",
                       exc_info=True)


async def seed_schedule() -> None:
    """Post-all-apps-loaded one-shot seeder, registered via ``hooks.register_hooks``.

    Runs after the platform has loaded every app, so the schedules app has run its
    migrations and its tables exist — this app loads before it alphabetically. This is also
    what gives an install that predates the fix its missing row, with nobody having to touch
    anything.
    """
    import asyncio
    await asyncio.to_thread(ensure_schedule)
