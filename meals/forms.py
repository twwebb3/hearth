from datetime import date

from django import forms


MEAL_TYPE_CHOICES = [
    ("breakfast", "Breakfast"),
    ("lunch", "Lunch"),
    ("dinner", "Dinner"),
    ("snack", "Snack"),
]


class MealForm(forms.Form):
    name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Meal name"}),
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    meal_type = forms.ChoiceField(
        choices=MEAL_TYPE_CHOICES,
        initial="dinner",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Optional notes..."}),
    )

    def clean_date(self):
        meal_date = self.cleaned_data.get("date")
        if meal_date and meal_date.year < 2000:
            raise forms.ValidationError("Please enter a valid date.")
        return meal_date
