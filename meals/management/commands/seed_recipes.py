from django.core.management.base import BaseCommand

from meals.models import Recipe


class Command(BaseCommand):
    help = "Seed the database with sample recipes for testing"

    def handle(self, *args, **options):
        recipes = [
            # Main dishes
            {"name": "Grilled Chicken", "kind": "MAIN", "notes": "Marinate for at least 2 hours"},
            {"name": "Spaghetti Bolognese", "kind": "MAIN", "notes": "Classic Italian meat sauce"},
            {"name": "Beef Tacos", "kind": "MAIN", "notes": "Serve with fresh salsa"},
            {"name": "Salmon Teriyaki", "kind": "MAIN", "notes": "Glaze while cooking"},
            {"name": "Chicken Stir Fry", "kind": "MAIN", "notes": "Use high heat for best results"},
            {"name": "Pork Chops", "kind": "MAIN", "notes": "Brine for extra juiciness"},
            # Side dishes
            {"name": "Roasted Broccoli", "kind": "SIDE", "notes": "425°F for 20 minutes"},
            {"name": "Mashed Potatoes", "kind": "SIDE", "notes": "Add butter and cream"},
            {"name": "Garden Salad", "kind": "SIDE", "notes": "Use seasonal vegetables"},
            {"name": "Steamed Rice", "kind": "SIDE", "notes": "1:2 ratio rice to water"},
            {"name": "Grilled Asparagus", "kind": "SIDE", "notes": "Drizzle with olive oil"},
            {"name": "Cornbread", "kind": "SIDE", "notes": "Serve warm with butter"},
        ]

        created_count = 0
        for recipe_data in recipes:
            recipe, created = Recipe.objects.get_or_create(
                name=recipe_data["name"],
                defaults={
                    "kind": recipe_data["kind"],
                    "notes": recipe_data["notes"],
                    "active": True,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f"  Created: {recipe.name} ({recipe.kind})")
            else:
                self.stdout.write(f"  Exists: {recipe.name} ({recipe.kind})")

        self.stdout.write(
            self.style.SUCCESS(f"\nDone! Created {created_count} new recipes.")
        )
