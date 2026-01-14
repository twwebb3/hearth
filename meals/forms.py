from django import forms

from .models import MealPlan, MealRating, Recipe


class MealPlanForm(forms.ModelForm):
    class Meta:
        model = MealPlan
        fields = ["date", "main_recipe", "side_recipe", "notes", "status"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional notes..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter to only show active recipes of the appropriate kind
        self.fields["main_recipe"].queryset = Recipe.objects.filter(active=True, kind="MAIN")
        self.fields["side_recipe"].queryset = Recipe.objects.filter(active=True, kind="SIDE")
        self.fields["main_recipe"].required = False
        self.fields["side_recipe"].required = False


class RecipeForm(forms.ModelForm):
    class Meta:
        model = Recipe
        fields = ["name", "kind", "notes", "active"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional notes..."}),
        }


class MealRatingForm(forms.ModelForm):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    rating = forms.ChoiceField(
        choices=RATING_CHOICES,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = MealRating
        fields = ["rating", "would_repeat", "comment"]
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 2, "placeholder": "Optional comment..."}),
        }
