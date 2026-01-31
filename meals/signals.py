from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import MealPlan, MealRating


def _sync_combo_for_meal_plan(meal_plan):
    """Upsert a Combo for this meal plan's recipe pair and refresh its stats.

    Skips silently when either recipe is missing.
    """
    if not meal_plan.main_recipe_id or not meal_plan.side_recipe_id:
        return

    # Import here to avoid circular import (services imports models).
    from .services import get_or_create_combo, refresh_combo_stats

    combo, _ = get_or_create_combo(
        main_recipe_id=meal_plan.main_recipe_id,
        side_recipe_id=meal_plan.side_recipe_id,
    )
    refresh_combo_stats(combo)


@receiver(post_save, sender=MealPlan)
def on_meal_plan_save(sender, instance, **kwargs):
    """Refresh combo stats when a MealPlan is finalized or unfinalized."""
    _sync_combo_for_meal_plan(instance)


@receiver(post_save, sender=MealRating)
def on_meal_rating_save(sender, instance, **kwargs):
    """Refresh combo stats when a MealRating is created or updated."""
    _sync_combo_for_meal_plan(instance.meal_plan)


@receiver(post_delete, sender=MealRating)
def on_meal_rating_delete(sender, instance, **kwargs):
    """Refresh combo stats when a MealRating is deleted."""
    _sync_combo_for_meal_plan(instance.meal_plan)
