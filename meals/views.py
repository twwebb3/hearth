from datetime import date, timedelta

from django.http import HttpResponse
from django.shortcuts import render

from . import services


def week_view(request):
    today = date.today()
    # Sunday is first day of week
    start_date = today - timedelta(days=(today.weekday() + 1) % 7)

    meals = services.get_meals_for_week(start_date)

    # Build list of days with their meals
    days = []
    for i in range(7):
        day_date = start_date + timedelta(days=i)
        day_meals = [m for m in meals if m["date"] == day_date]
        days.append({
            "date": day_date,
            "meals": day_meals,
        })

    return render(request, "meals/week.html", {
        "start_date": start_date,
        "end_date": start_date + timedelta(days=6),
        "days": days,
    })


def meal_detail(request, pk):
    return HttpResponse(f"Meal detail: {pk}")


def meal_create(request):
    return HttpResponse("Meal create")


def meal_edit(request, pk):
    return HttpResponse(f"Meal edit: {pk}")


def ingredient_add(request, meal_pk):
    return HttpResponse(f"Add ingredient to meal: {meal_pk}")


def ingredient_toggle(request, pk):
    return HttpResponse(f"Toggle ingredient: {pk}")
