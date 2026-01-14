from datetime import timedelta

from .models import MealPlan, MealRating, Recipe


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
