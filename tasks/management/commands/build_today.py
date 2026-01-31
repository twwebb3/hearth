import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from tasks.services import generate_instances_for_date, rollover_incomplete


class Command(BaseCommand):
    help = (
        "Generate today's scheduled task instances and optionally "
        "roll over yesterday's incomplete items."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-rollover",
            action="store_true",
            default=False,
            help="Skip rolling over yesterday's incomplete instances.",
        )
        parser.add_argument(
            "--date",
            type=datetime.date.fromisoformat,
            default=None,
            help="Target date (YYYY-MM-DD). Defaults to today.",
        )

    def handle(self, *args, **options):
        target = options["date"] or timezone.localdate()
        yesterday = target - datetime.timedelta(days=1)

        # 1. Generate scheduled instances
        generated = generate_instances_for_date(target)
        self.stdout.write(f"Generated {len(generated)} scheduled instance(s) for {target}.")
        for task in generated:
            self.stdout.write(f"  + {task.name}")

        # 2. Rollover
        if options["no_rollover"]:
            self.stdout.write("Rollover skipped (--no-rollover).")
        else:
            rolled = rollover_incomplete(yesterday, target)
            self.stdout.write(
                f"Rolled over {len(rolled)} incomplete instance(s) "
                f"from {yesterday}."
            )
            for inst in rolled:
                self.stdout.write(f"  ~ {inst.task.name}")

        self.stdout.write(self.style.SUCCESS("Done."))
