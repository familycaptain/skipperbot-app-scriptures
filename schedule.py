"""Ask the platform to run the nightly preparation pass.

Recurring work on this platform needs a `schedules` row linked to a `job_type`. This app
shipped without one — no seed migration, no lifecycle hook, no declared job types — and the
platform referenced `scripture_prefetch` nowhere except the handler registration. So a fresh
install never ran the pass at all; chapters were only prepared when somebody opened them.

An install that has been around a while can be in a different state: a row for this job type
may already exist, created by hand or by an earlier version, under an id this module would
never guess. That is why the reconcile keys on the JOB TYPE rather than on our own id — it
adopts what is there instead of adding a second row and running the pass twice a night.

`ensure_schedule()` is idempotent and safe to call on every boot: it reconciles rather than
re-creating, so it does not drift the fire time.
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


def _existing_rows(_sched) -> list[dict]:
    """Every schedule already pointing at our job type, whatever id it carries.

    Looked up by JOB TYPE rather than by our own id on purpose. An install that predates
    this module can already have a schedule for the nightly pass — created by hand, or by
    an earlier version of the app — under an id we would never guess. Keying only on our
    own id would leave that one in place and add a second, so the pass would run twice a
    night, doing the same work and spending the same model calls twice.
    """
    try:
        rows = _sched.list_schedules(active_only=False, limit=500) or []
    except Exception:
        logger.debug("SCRIPTURES: could not list schedules", exc_info=True)
        return []
    return [r for r in rows if (r.get("linked_entity_id") or "") == JOB_TYPE]


def ensure_schedule() -> None:
    """Create, adopt or reconcile the nightly preparation schedule. Never raises.

    Always active. A household with no bookmarks is not a reason to switch the schedule off:
    bookmarks come and go, the pass already answers "no bookmarks found — nothing to
    prefetch" in that case, and a schedule that disables itself is a second thing to debug
    when preparation stops happening.
    """
    try:
        from apps.schedules import data as _sched

        found = _existing_rows(_sched)
        ours = next((r for r in found if r.get("id") == SCHEDULE_ID), None)
        # Prefer our own row if it is there; otherwise ADOPT the one that already exists
        # rather than adding another. Oldest first, so the choice is stable across boots.
        target = ours or (sorted(found, key=lambda r: str(r.get("created_at") or ""))[0]
                          if found else None)
        target_id = (target or {}).get("id") or SCHEDULE_ID

        if target and target_id != SCHEDULE_ID:
            logger.info("SCRIPTURES: adopting existing nightly schedule %s rather than "
                        "creating a second one", target_id)

        # Reset the countdown only on first creation, re-activation, or a time change, so a
        # plain reconcile on every boot does not push tonight's run later each time.
        reset = (
            target is None
            or not target.get("active")
            or target.get("time_of_day") != TIME_OF_DAY
        )
        next_due = _sched.compute_next_due("daily", {"every": 1}, TIME_OF_DAY) if reset else None

        _sched.upsert_schedule(
            target_id,
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

        # Anything else pointing at the same job type would run the pass a second time the
        # same night. Deactivated rather than deleted: reversible, visible in the app, and
        # it never destroys a row somebody may have made deliberately.
        for row in found:
            rid = row.get("id")
            if rid and rid != target_id and row.get("active"):
                try:
                    _sched.upsert_schedule(rid, title=row.get("title") or "Scripture prefetch (duplicate)",
                                           active=False)
                    logger.warning("SCRIPTURES: deactivated duplicate nightly schedule %s — "
                                   "the pass is scheduled once, on %s", rid, target_id)
                except Exception:
                    logger.warning("SCRIPTURES: could not deactivate duplicate schedule %s",
                                   rid, exc_info=True)

        logger.info("SCRIPTURES: nightly preparation scheduled for %s on %s",
                    TIME_OF_DAY, target_id)
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
