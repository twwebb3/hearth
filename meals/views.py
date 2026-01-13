from datetime import date, datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import redirect, render

from . import services
from .forms import MealForm


def _check_meal_owner(meal, user):
    """Return True if user owns the meal, False otherwise."""
    return meal.get("created_by_username") == user.username


@login_required
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


@login_required
def meal_detail(request, pk):
    meal = services.get_meal(pk)
    if meal is None:
        raise Http404("Meal not found")
    return render(request, "meals/meal_detail.html", {"meal": meal})


@login_required
def meal_create(request):
    initial = {}
    # Pre-fill date from querystring if provided
    date_str = request.GET.get("date")
    if date_str:
        try:
            initial["date"] = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    if request.method == "POST":
        form = MealForm(request.POST)
        if form.is_valid():
            meal = services.create_meal({
                "name": form.cleaned_data["name"],
                "date": form.cleaned_data["date"],
                "meal_type": form.cleaned_data["meal_type"],
                "notes": form.cleaned_data["notes"],
            }, username=request.user.username)
            return redirect("meals:meal_detail", pk=meal["id"])
    else:
        form = MealForm(initial=initial)

    return render(request, "meals/meal_form.html", {
        "form": form,
        "title": "Add Meal",
        "submit_label": "Create Meal",
    })


@login_required
def meal_edit(request, pk):
    meal = services.get_meal(pk)
    if meal is None:
        raise Http404("Meal not found")

    if not _check_meal_owner(meal, request.user):
        return HttpResponseForbidden("You do not have permission to edit this meal.")

    if request.method == "POST":
        form = MealForm(request.POST)
        if form.is_valid():
            services.update_meal(pk, {
                "name": form.cleaned_data["name"],
                "date": form.cleaned_data["date"],
                "meal_type": form.cleaned_data["meal_type"],
                "notes": form.cleaned_data["notes"],
            })
            return redirect("meals:meal_detail", pk=pk)
    else:
        form = MealForm(initial={
            "name": meal["name"],
            "date": meal["date"],
            "meal_type": meal["meal_type"],
            "notes": meal.get("notes", ""),
        })

    return render(request, "meals/meal_form.html", {
        "form": form,
        "meal": meal,
        "title": "Edit Meal",
        "submit_label": "Save Changes",
    })


@login_required
def ingredient_add(request, meal_pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    meal = services.get_meal(meal_pk)
    if meal is None:
        raise Http404("Meal not found")

    if not _check_meal_owner(meal, request.user):
        return HttpResponseForbidden("You do not have permission to modify this meal.")

    name = request.POST.get("name", "").strip()
    quantity = request.POST.get("quantity", "").strip()

    if name:
        services.add_ingredient(meal_pk, {
            "name": name,
            "quantity": quantity,
        })

    return redirect("meals:meal_detail", pk=meal_pk)


@login_required
def ingredient_toggle(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    meal_id = request.POST.get("meal_id")
    if not meal_id:
        raise Http404("Meal ID required")

    try:
        meal_id = int(meal_id)
    except ValueError:
        raise Http404("Invalid meal ID")

    meal = services.get_meal(meal_id)
    if meal is None:
        raise Http404("Meal not found")

    if not _check_meal_owner(meal, request.user):
        return HttpResponseForbidden("You do not have permission to modify this meal.")

    result = services.toggle_ingredient(meal_id, pk)
    if result is None:
        raise Http404("Ingredient not found")

    # Redirect to referer if present, otherwise to meal detail
    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect("meals:meal_detail", pk=meal_id)
