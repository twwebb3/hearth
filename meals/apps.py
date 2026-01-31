import os
import sys

from django.apps import AppConfig


class MealsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "meals"

    def ready(self):
        import meals.signals  # noqa: F401

        self._rebuild_combos_on_dev_startup()

    @staticmethod
    def _rebuild_combos_on_dev_startup():
        """Run rebuild_combos once when `runserver` starts in DEBUG mode."""
        from django.conf import settings

        if not settings.DEBUG or "runserver" not in sys.argv:
            return

        # With the auto-reloader Django spawns two processes; RUN_MAIN
        # marks the child that actually serves requests.  Without the
        # reloader (--noreload) the env var is absent, so we run then too.
        if os.environ.get("RUN_MAIN") != "true" and "--noreload" not in sys.argv:
            return

        from django.core.management import call_command

        call_command("rebuild_combos", "--quiet")
