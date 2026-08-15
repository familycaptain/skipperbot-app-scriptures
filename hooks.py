"""Scriptures — platform hooks.

Registers the nightly-preparation seeder as a lifecycle background task so it runs ONCE
after every app has loaded.

Why not at import time: this app loads before the schedules app alphabetically, so the
`app_schedules` tables may not exist yet when this module is imported. Lifecycle background
tasks are started by the platform after `load_all_apps()`. The seeder is fail-closed and
guards a not-yet-created table, so boot can never crash on it.

Called by the app loader during startup via ``register_hooks()``.
"""


def register_hooks():
    """Register the one-shot preparation-schedule seeder with the platform lifecycle."""
    from app_platform.lifecycle import register_background_task
    from apps.scriptures.schedule import seed_schedule

    # Pass the coroutine FUNCTION (zero-arg factory), NOT seed_schedule().
    register_background_task("scriptures_schedule_seed", seed_schedule)
