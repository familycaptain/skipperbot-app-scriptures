"""The nightly preparation pass is actually asked for.

`prefetch_scripture_summaries()` has always worked and its handler has always been
registered with the dispatcher — but nothing anywhere queued it. Recurring work needs a
`schedules` row linked to a job type, and this app had no seed migration, no lifecycle hook
and declared no job types, while the platform mentioned `scripture_prefetch` nowhere except
the handler registration. So the pass documented as nightly had never run on any install,
and chapters were only ever prepared when somebody opened them.

The bug was a missing CALLER, not broken work, so these test the calling — that a row is
created, that it points at the job type the dispatcher polls, and that reconciling on every
boot does not push tonight's run later each time.

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

    def get_schedule(self, sid):
        return self.rows.get(sid)

    def compute_next_due(self, rtype, rule, tod):
        return f"next:{tod}"

    def upsert_schedule(self, sid, **kw):
        self.calls.append(sid)
        self.rows[sid] = dict(kw)
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
