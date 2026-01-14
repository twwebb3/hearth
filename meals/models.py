from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


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
