"""The nightly preparation pass is actually asked for.

`prefetch_scripture_summaries()` has always worked and its handler has always been
registered with the dispatcher — but the app shipped nothing that would ASK for it. No seed
migration, no lifecycle hook, no declared job types, and the platform mentioned
`scripture_prefetch` nowhere except the handler registration. On a fresh install the pass
therefore never ran, and chapters were only prepared when somebody opened them.

A long-running install can be in a different state: a row for this job type may already
exist under an id this module would never guess, created by hand or by an earlier version.
Reconciling on our own id alone would leave that one running and add a second, so the pass
would run twice a night — the same work and the same model spend, twice. That case has its
own class below, and it is the one that bites an install that has been alive for months.

Offline: the schedules data layer is stubbed.

Run: python3 -m unittest apps.scriptures.tests.test_nightly_preparation_is_scheduled
"""
import sys
import unittest
from unittest import mock

from apps.scriptures import schedule as sched


class _FakeSchedules:
    def __init__(self, existing=None):
        self.rows = dict(existing or {})
        self.calls = []

    def list_schedules(self, active_only=True, limit=200):
        out = []
        for sid, row in self.rows.items():
            if active_only and not row.get("active"):
                continue
            out.append({**row, "id": sid})
        return out

    def get_schedule(self, sid):
        return self.rows.get(sid)

    def compute_next_due(self, rtype, rule, tod):
        return f"next:{tod}"

    def upsert_schedule(self, sid, **kw):
        self.calls.append(sid)
        # Upsert semantics: merge, so a partial update (deactivating a duplicate) does not
        # wipe the rest of the row.
        self.rows[sid] = {**self.rows.get(sid, {}), **kw}
        return self.rows[sid]


def _run(existing=None):
    fake = _FakeSchedules(existing)
    with mock.patch.dict(sys.modules, {"apps.schedules.data": fake}):
        sched.ensure_schedule()
    return fake


class ThePassIsScheduled(unittest.TestCase):
    def test_a_row_is_created(self):
        fake = _run()
        self.assertIn(sched.SCHEDULE_ID, fake.rows)

    def test_it_points_at_the_job_type_the_dispatcher_polls(self):
        # Without this link the row exists and is inert — which is a different way to have
        # the same bug.
        row = _run().rows[sched.SCHEDULE_ID]
        self.assertEqual(row["linked_entity_id"], "scripture_prefetch")
        self.assertEqual(row["linked_entity_type"], "job")

    def test_it_runs_nightly_at_three(self):
        row = _run().rows[sched.SCHEDULE_ID]
        self.assertEqual(row["time_of_day"], "03:00")
        self.assertEqual(row["recurrence_type"], "daily")
        self.assertEqual(row["recurrence_rule"], {"every": 1})

    def test_it_is_always_active(self):
        # Deliberately not conditional on there being bookmarks: the pass already answers
        # "nothing to prefetch" for an empty household, and a schedule that switches itself
        # off is a second thing to debug when preparation stops happening.
        self.assertTrue(_run().rows[sched.SCHEDULE_ID]["active"])

    def test_it_does_not_collide_with_the_nightly_backup(self):
        # Both are heavy and the preparation pass makes a model call per missing item.
        self.assertNotEqual(sched.TIME_OF_DAY, "02:00")


class ReconcilingIsSafeToRepeat(unittest.TestCase):
    def test_a_second_pass_does_not_drift_the_fire_time(self):
        fake = _FakeSchedules()
        with mock.patch.dict(sys.modules, {"apps.schedules.data": fake}):
            sched.ensure_schedule()
            first = dict(fake.rows[sched.SCHEDULE_ID])
            sched.ensure_schedule()
            second = fake.rows[sched.SCHEDULE_ID]
        self.assertIsNotNone(first["next_due"], "first creation must set a countdown")
        self.assertIsNone(second["next_due"], "a plain reconcile must leave the countdown alone")

    def test_an_inactive_row_is_reactivated_with_a_fresh_countdown(self):
        fake = _run({sched.SCHEDULE_ID: {"active": False, "time_of_day": "03:00"}})
        row = fake.rows[sched.SCHEDULE_ID]
        self.assertTrue(row["active"])
        self.assertIsNotNone(row["next_due"])

    def test_a_changed_time_resets_the_countdown(self):
        fake = _run({sched.SCHEDULE_ID: {"active": True, "time_of_day": "23:00"}})
        self.assertIsNotNone(fake.rows[sched.SCHEDULE_ID]["next_due"])


class AnExistingScheduleIsAdoptedNotDuplicated(unittest.TestCase):
    """The state a long-running install is actually in.

    A row for this job type can already exist under an id this module would never guess —
    made by hand, or by an earlier version. Keying only on our own id would leave it in
    place and add a second, so the pass would run twice a night: the same work, and the same
    model spend, twice.
    """

    PRIOR = {"sch-701a1058": {"title": "Scriptures nightly prefetch",
                              "linked_entity_id": "scripture_prefetch",
                              "linked_entity_type": "job",
                              "active": True, "time_of_day": "02:00",
                              "created_at": "2026-04-18"}}

    def test_the_existing_row_is_reused_and_no_second_one_is_created(self):
        fake = _run(self.PRIOR)
        self.assertIn("sch-701a1058", fake.rows)
        self.assertNotIn(sched.SCHEDULE_ID, fake.rows,
                         "a second schedule was created — the pass would run twice a night")

    def test_the_adopted_row_is_moved_to_the_canonical_time(self):
        fake = _run(self.PRIOR)
        row = fake.rows["sch-701a1058"]
        self.assertEqual(row["time_of_day"], sched.TIME_OF_DAY)
        self.assertTrue(row["active"])
        self.assertIsNotNone(row["next_due"], "a time change must reset the countdown")

    def test_our_own_row_wins_when_both_exist(self):
        both = {**self.PRIOR,
                sched.SCHEDULE_ID: {"linked_entity_id": "scripture_prefetch",
                                    "active": True, "time_of_day": "03:00",
                                    "created_at": "2026-08-15"}}
        fake = _run(both)
        self.assertTrue(fake.rows[sched.SCHEDULE_ID]["active"])
        self.assertFalse(fake.rows["sch-701a1058"]["active"],
                         "the duplicate was left running")

    def test_a_duplicate_is_deactivated_not_deleted(self):
        # Reversible and visible in the app — never destroy a row somebody made on purpose.
        both = {**self.PRIOR,
                sched.SCHEDULE_ID: {"linked_entity_id": "scripture_prefetch",
                                    "active": True, "time_of_day": "03:00",
                                    "created_at": "2026-08-15"}}
        fake = _run(both)
        self.assertIn("sch-701a1058", fake.rows, "the duplicate row was deleted")
        self.assertFalse(fake.rows["sch-701a1058"]["active"])

    def test_exactly_one_schedule_is_left_active(self):
        for existing in ({}, self.PRIOR,
                         {**self.PRIOR, "sch-other": {"linked_entity_id": "scripture_prefetch",
                                                      "active": True, "time_of_day": "05:00",
                                                      "created_at": "2026-05-01"}}):
            with self.subTest(n=len(existing)):
                fake = _run(existing)
                live = [sid for sid, r in fake.rows.items()
                        if r.get("linked_entity_id") == "scripture_prefetch" and r.get("active")]
                self.assertEqual(len(live), 1, f"expected one active schedule, got {live}")

    def test_schedules_for_other_jobs_are_untouched(self):
        other = {"sch-backup-nightly": {"linked_entity_id": "backup", "active": True,
                                        "time_of_day": "02:00", "created_at": "2026-01-01"}}
        fake = _run(other)
        self.assertTrue(fake.rows["sch-backup-nightly"]["active"])
        self.assertEqual(fake.rows["sch-backup-nightly"]["time_of_day"], "02:00")


class ItNeverBreaksBoot(unittest.TestCase):
    def test_a_failing_schedules_layer_is_swallowed(self):
        # This runs during startup. A scheduling problem must not take the platform down;
        # the next boot reconciles anyway.
        boom = mock.MagicMock()
        boom.upsert_schedule.side_effect = RuntimeError("db down")
        with mock.patch.dict(sys.modules, {"apps.schedules.data": boom}):
            sched.ensure_schedule()   # must not raise

    def test_a_missing_schedules_table_is_treated_as_not_yet_created(self):
        fake = _FakeSchedules()
        fake.get_schedule = mock.MagicMock(side_effect=RuntimeError("no such table"))
        with mock.patch.dict(sys.modules, {"apps.schedules.data": fake}):
            sched.ensure_schedule()
        self.assertIn(sched.SCHEDULE_ID, fake.rows)


class TheSeederIsRegisteredWithTheLifecycle(unittest.TestCase):
    """The row is only created if something calls ensure_schedule at startup."""

    def test_hooks_registers_the_seeder_after_all_apps_load(self):
        from apps.scriptures import hooks
        lifecycle = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"app_platform.lifecycle": lifecycle}):
            hooks.register_hooks()
        lifecycle.register_background_task.assert_called_once()
        name, fn = lifecycle.register_background_task.call_args[0]
        self.assertEqual(name, "scriptures_schedule_seed")
        # The FUNCTION, not the coroutine — passing seed_schedule() would never be awaited.
        self.assertTrue(callable(fn))
        self.assertFalse(hasattr(fn, "__await__"))


if __name__ == "__main__":
    unittest.main()
