from django.contrib import admin

from .models import MealPlan, MealRating, Recipe


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
