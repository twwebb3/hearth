from django.core.management.base import BaseCommand

from tasks.models import Domain

DOMAINS = [
    {"name": "House \u2013 Exterior", "sort_order": 10, "color_hex": "#E74C3C"},
    {"name": "House \u2013 Interior", "sort_order": 20, "color_hex": "#3498DB"},
    {"name": "Day Job", "sort_order": 30, "color_hex": "#2ECC71"},
    {"name": "Family", "sort_order": 40, "color_hex": "#F39C12"},
    {"name": "Personal Learning", "sort_order": 50, "color_hex": "#9B59B6"},
    {"name": "Spiritual Rule of Life", "sort_order": 60, "color_hex": "#1ABC9C"},
]


class Command(BaseCommand):
    help = "Seed the initial set of task domains."

    def handle(self, *args, **options):
        for entry in DOMAINS:
            _, created = Domain.objects.update_or_create(
                name=entry["name"],
                defaults={
                    "sort_order": entry["sort_order"],
                    "color_hex": entry["color_hex"],
                },
            )
            status = "created" if created else "already exists"
            self.stdout.write(f"  {entry['name']} – {status}")

        self.stdout.write(self.style.SUCCESS("Done."))
