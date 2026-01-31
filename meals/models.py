from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Exists, OuterRef


class Recipe(models.Model):
    KIND_CHOICES = [
        ("MAIN", "Main"),
        ("SIDE", "Side"),
    ]

    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=4, choices=KIND_CHOICES)
    notes = models.TextField(blank=True, default="")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class MealPlan(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("FINALIZED", "Finalized"),
    ]

    date = models.DateField(unique=True)
    main_recipe = models.ForeignKey(
        Recipe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mealplans_as_main",
    )
    side_recipe = models.ForeignKey(
        Recipe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mealplans_as_side",
    )
    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="DRAFT")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="meal_plans",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"MealPlan for {self.date}"


class MealRating(models.Model):
    meal_plan = models.OneToOneField(
        MealPlan,
        on_delete=models.CASCADE,
        related_name="rating",
    )
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    would_repeat = models.BooleanField()
    comment = models.TextField(blank=True, default="")
    rated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Rating {self.rating}/5 for {self.meal_plan.date}"


class ComboQuerySet(models.QuerySet):
    def qualified(self):
        """Return only combos that have at least one finalized MealPlan with a rating."""
        return self.filter(
            Exists(
                MealPlan.objects.filter(
                    main_recipe=OuterRef("main_recipe"),
                    side_recipe=OuterRef("side_recipe"),
                    status="FINALIZED",
                    rating__isnull=False,
                )
            )
        )


class Combo(models.Model):
    """A household-wide pairing of a main recipe and a side recipe.

    A Combo is considered "qualified" when at least one finalized MealPlan
    with a MealRating exists for the pairing.
    """

    main_recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name="combos_as_main",
        limit_choices_to={"kind": "MAIN"},
    )
    side_recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name="combos_as_side",
        limit_choices_to={"kind": "SIDE"},
    )
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ComboQuerySet.as_manager()

    class Meta:
        unique_together = [("main_recipe", "side_recipe")]
        ordering = ["main_recipe__name", "side_recipe__name"]

    def __str__(self):
        return f"{self.main_recipe} + {self.side_recipe}"

    def meal_plans(self):
        """Return all MealPlans that used this combo."""
        return MealPlan.objects.filter(
            main_recipe=self.main_recipe,
            side_recipe=self.side_recipe,
        ).select_related("main_recipe", "side_recipe", "created_by")

    def rated_meal_plans(self):
        """Return finalized MealPlans with ratings for this combo."""
        return self.meal_plans().filter(
            status="FINALIZED",
            rating__isnull=False,
        )


class ComboStats(models.Model):
    """Denormalized aggregate metrics for a Combo, household-wide."""

    combo = models.OneToOneField(
        Combo,
        on_delete=models.CASCADE,
        related_name="stats",
    )
    times_made = models.PositiveIntegerField(default=0)
    avg_rating = models.FloatField(default=0.0)
    would_repeat_rate = models.FloatField(default=0.0)
    last_made_at = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "combo stats"

    def __str__(self):
        return f"Stats for {self.combo} ({self.times_made}x, avg {self.avg_rating:.1f})"

    def refresh_from_plans(self):
        """Recompute all fields from the combo's rated meal plans."""
        from django.db.models import Avg, Count, Max, Q

        aggregates = self.combo.rated_meal_plans().aggregate(
            count=Count("id"),
            average=Avg("rating__rating"),
            repeat_count=Count("id", filter=Q(rating__would_repeat=True)),
            latest=Max("date"),
        )

        self.times_made = aggregates["count"]
        self.avg_rating = round(aggregates["average"] or 0.0, 2)
        self.would_repeat_rate = (
            round(aggregates["repeat_count"] / aggregates["count"], 2)
            if aggregates["count"]
            else 0.0
        )
        self.last_made_at = aggregates["latest"]
        self.save()
