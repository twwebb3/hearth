from django.contrib import admin

from .models import Combo, ComboStats, MealPlan, MealRating, Recipe


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "active", "created_at"]
    list_filter = ["kind", "active"]
    search_fields = ["name"]


@admin.register(MealPlan)
class MealPlanAdmin(admin.ModelAdmin):
    list_display = ["date", "main_recipe", "side_recipe", "status", "created_by"]
    list_filter = ["status", "date"]
    date_hierarchy = "date"


@admin.register(MealRating)
class MealRatingAdmin(admin.ModelAdmin):
    list_display = ["meal_plan", "rating", "would_repeat", "rated_at"]
    list_filter = ["rating", "would_repeat"]


@admin.register(Combo)
class ComboAdmin(admin.ModelAdmin):
    list_display = ["main_recipe", "side_recipe", "archived", "created_at"]
    list_filter = ["archived", "main_recipe", "side_recipe"]
    actions = ["archive_combos", "unarchive_combos"]

    @admin.action(description="Archive selected combos")
    def archive_combos(self, request, queryset):
        updated = queryset.update(archived=True)
        self.message_user(request, f"{updated} combo(s) archived.")

    @admin.action(description="Unarchive selected combos")
    def unarchive_combos(self, request, queryset):
        updated = queryset.update(archived=False)
        self.message_user(request, f"{updated} combo(s) unarchived.")


@admin.register(ComboStats)
class ComboStatsAdmin(admin.ModelAdmin):
    list_display = ["combo", "times_made", "avg_rating", "would_repeat_rate", "last_made_at"]
    list_filter = ["times_made"]
    readonly_fields = ["combo", "times_made", "avg_rating", "would_repeat_rate", "last_made_at", "updated_at"]
