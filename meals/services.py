from datetime import date as date_type
from datetime import timedelta

from django.db.models import Exists, OuterRef

from .models import Combo, ComboStats, MealPlan, MealRating, Recipe

# How many days a combo must "rest" before suggest_top_combo() recommends it again.
TOP_COMBO_COOLDOWN_DAYS = 14


def _meal_plan_queryset():
    """Base queryset with common joins for MealPlan."""
    return MealPlan.objects.select_related(
        "main_recipe", "side_recipe", "created_by"
    ).prefetch_related("rating")


def get_meals_for_week(start_date):
    """Return all meal plans for the 7-day period starting at start_date.

    Returns MealPlan queryset joined with recipes and ratings.
    """
    end_date = start_date + timedelta(days=6)
    return _meal_plan_queryset().filter(
        date__gte=start_date, date__lte=end_date
    ).order_by("date")


# Alias for backwards compatibility
get_meal_plans_for_week = get_meals_for_week


def get_meal_plan(meal_plan_id=None, date=None):
    """Return a single meal plan by ID or date, or None if not found.

    Args:
        meal_plan_id: Primary key of the meal plan
        date: Date of the meal plan

    Returns:
        MealPlan instance or None
    """
    try:
        if meal_plan_id is not None:
            return _meal_plan_queryset().get(pk=meal_plan_id)
        elif date is not None:
            return _meal_plan_queryset().get(date=date)
        else:
            return None
    except MealPlan.DoesNotExist:
        return None


def get_meal_plan_by_date(date):
    """Return the meal plan for a specific date, or None if not found."""
    return get_meal_plan(date=date)


def create_meal_plan(date, user, main_recipe=None, side_recipe=None, notes="", status="DRAFT"):
    """Create a new meal plan for a date.

    Args:
        date: The date for this meal plan
        user: The user creating the plan
        main_recipe: Optional Recipe instance for main dish
        side_recipe: Optional Recipe instance for side dish
        notes: Optional notes string
        status: Status string (DRAFT or FINALIZED)

    Returns:
        The created MealPlan instance
    """
    return MealPlan.objects.create(
        date=date,
        main_recipe=main_recipe,
        side_recipe=side_recipe,
        notes=notes,
        status=status,
        created_by=user,
    )


def update_meal_plan(meal_plan, main_recipe=None, side_recipe=None, notes=None, status=None):
    """Update an existing meal plan.

    Args:
        meal_plan: The MealPlan instance to update
        main_recipe: New main recipe (or None to skip)
        side_recipe: New side recipe (or None to skip)
        notes: New notes (or None to skip)
        status: New status (or None to skip)

    Returns:
        The updated MealPlan instance
    """
    if main_recipe is not None:
        meal_plan.main_recipe = main_recipe
    if side_recipe is not None:
        meal_plan.side_recipe = side_recipe
    if notes is not None:
        meal_plan.notes = notes
    if status is not None:
        meal_plan.status = status
    meal_plan.save()
    return meal_plan


def finalize_meal_plan(meal_plan):
    """Set meal plan status to FINALIZED."""
    meal_plan.status = "FINALIZED"
    meal_plan.save()
    return meal_plan


def unfinalize_meal_plan(meal_plan):
    """Set meal plan status back to DRAFT."""
    meal_plan.status = "DRAFT"
    meal_plan.save()
    return meal_plan


def get_or_create_meal_plan(date, user):
    """Get existing meal plan for date or create a new draft.

    Returns:
        Tuple of (MealPlan, created_bool)
    """
    return MealPlan.objects.get_or_create(
        date=date,
        defaults={"created_by": user, "status": "DRAFT"},
    )


def create_or_update_rating(meal_plan, rating, would_repeat, comment=""):
    """Create or update a rating for a meal plan.

    Args:
        meal_plan: The MealPlan to rate
        rating: Integer 1-5
        would_repeat: Boolean
        comment: Optional comment string

    Returns:
        The MealRating instance
    """
    meal_rating, created = MealRating.objects.update_or_create(
        meal_plan=meal_plan,
        defaults={
            "rating": rating,
            "would_repeat": would_repeat,
            "comment": comment,
        },
    )
    return meal_rating


def get_active_recipes(kind=None):
    """Return active recipes, optionally filtered by kind.

    Args:
        kind: Optional filter for recipe kind (MAIN or SIDE)

    Returns:
        QuerySet of active Recipe instances
    """
    qs = Recipe.objects.filter(active=True)
    if kind:
        qs = qs.filter(kind=kind)
    return qs.order_by("name")


def get_or_create_combo(main_recipe=None, side_recipe=None,
                        main_recipe_id=None, side_recipe_id=None):
    """Get or create a Combo for a (main, side) recipe pairing.

    Accepts either Recipe instances or raw IDs.

    Args:
        main_recipe: Recipe instance (kind=MAIN)
        side_recipe: Recipe instance (kind=SIDE)
        main_recipe_id: PK of the main Recipe
        side_recipe_id: PK of the side Recipe

    Returns:
        Tuple of (Combo, created_bool)
    """
    kwargs = {}
    if main_recipe is not None:
        kwargs["main_recipe"] = main_recipe
    elif main_recipe_id is not None:
        kwargs["main_recipe_id"] = main_recipe_id
    if side_recipe is not None:
        kwargs["side_recipe"] = side_recipe
    elif side_recipe_id is not None:
        kwargs["side_recipe_id"] = side_recipe_id
    return Combo.objects.get_or_create(**kwargs)


def get_combo(combo_id):
    """Return a single Combo by PK with recipes and stats, or None."""
    try:
        return Combo.objects.select_related(
            "main_recipe", "side_recipe", "stats",
        ).get(pk=combo_id)
    except Combo.DoesNotExist:
        return None


def toggle_combo_archived(combo):
    """Toggle a combo's archived state.

    Returns:
        The updated Combo instance.
    """
    combo.archived = not combo.archived
    combo.save(update_fields=["archived"])
    return combo


def get_qualified_combos(active_only=False, min_rating=None, exclude_archived=True):
    """Return all Combos that have at least one finalized, rated MealPlan.

    Sorted best-performing first: avg_rating desc, would_repeat_rate desc,
    times_made desc.

    Args:
        active_only: If True, only include combos where both recipes are active.
        min_rating: If set, exclude combos with avg_rating below this value.
        exclude_archived: If True (default), exclude archived combos.
    """
    qs = (
        Combo.objects.qualified()
        .select_related("main_recipe", "side_recipe", "stats")
        .filter(stats__times_made__gte=1)
        .order_by("-stats__avg_rating", "-stats__would_repeat_rate", "-stats__times_made")
    )
    if exclude_archived:
        qs = qs.filter(archived=False)
    if active_only:
        qs = qs.filter(main_recipe__active=True, side_recipe__active=True)
    if min_rating is not None:
        qs = qs.filter(stats__avg_rating__gte=min_rating)
    return qs


def suggest_top_combo(today=None):
    """Return the highest-ranked combo not planned in the last N days.

    "Planned" means any MealPlan row (any status) exists for the pair within
    the cooldown window.  Returns None when every combo was used recently or
    no qualified combos exist.

    Args:
        today: Override for the current date (useful in tests).
    """
    if today is None:
        today = date_type.today()

    cutoff = today - timedelta(days=TOP_COMBO_COOLDOWN_DAYS)

    recent_use = MealPlan.objects.filter(
        main_recipe_id=OuterRef("main_recipe_id"),
        side_recipe_id=OuterRef("side_recipe_id"),
        date__gte=cutoff,
    )

    return (
        get_qualified_combos(active_only=True, min_rating=3)
        .exclude(Exists(recent_use))
        .first()
    )


def refresh_combo_stats(combo):
    """Refresh (or create) the ComboStats row for a given Combo.

    Args:
        combo: Combo instance whose stats should be recomputed.

    Returns:
        The updated ComboStats instance.
    """
    stats, _ = ComboStats.objects.get_or_create(combo=combo)
    stats.refresh_from_plans()
    return stats


def get_rated_meal_plans(rating=None, would_repeat=None, recipe_search=None):
    """Return finalized meal plans with ratings, with optional filters.

    Args:
        rating: Filter by rating value (1-5)
        would_repeat: Filter by would_repeat boolean
        recipe_search: Search string for recipe names

    Returns:
        QuerySet of MealPlan instances
    """
    from django.db.models import Q

    qs = _meal_plan_queryset().filter(
        status="FINALIZED",
        rating__isnull=False,
    ).order_by("-date")

    if rating is not None:
        qs = qs.filter(rating__rating=rating)

    if would_repeat is not None:
        qs = qs.filter(rating__would_repeat=would_repeat)

    if recipe_search:
        qs = qs.filter(
            Q(main_recipe__name__icontains=recipe_search) |
            Q(side_recipe__name__icontains=recipe_search)
        )

    return qs
