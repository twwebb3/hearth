from django.core.management.base import BaseCommand

from meals.models import MealPlan
from meals.services import get_or_create_combo, refresh_combo_stats


class Command(BaseCommand):
    help = (
        "Rebuild Combo and ComboStats rows from finalized, rated MealPlans.\n\n"
        "Safe to run at any frequency; the command is fully idempotent.\n\n"
        "Production cron example (nightly at 3:00 AM):\n"
        "  0 3 * * * cd /path/to/hearth && .venv/bin/python manage.py rebuild_combos --quiet"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress per-combo output (still prints summary).",
        )

    def handle(self, *args, **options):
        quiet = options["quiet"]

        pairs = (
            MealPlan.objects.filter(
                status="FINALIZED",
                rating__isnull=False,
                main_recipe__isnull=False,
                side_recipe__isnull=False,
            )
            .values_list("main_recipe", "side_recipe")
            .distinct()
        )

        total = len(pairs)
        if total == 0:
            if not quiet:
                self.stdout.write("No qualifying meal plans found.")
            return

        created_count = 0
        for main_id, side_id in pairs:
            combo, created = get_or_create_combo(
                main_recipe_id=main_id,
                side_recipe_id=side_id,
            )
            if created:
                created_count += 1
            stats = refresh_combo_stats(combo)
            if not quiet:
                self.stdout.write(
                    f"  {'Created' if created else 'Updated'}: {combo} "
                    f"({stats.times_made}x, avg {stats.avg_rating:.1f})"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"rebuild_combos: {total} combos processed "
                f"({created_count} new, {total - created_count} existing)."
            )
        )
