"""
Meals views.

All views require authentication via @login_required.
This is a household-wide app, so any authenticated user can
create, edit, finalize, and rate any meal plan.
"""
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render

from . import services
from .forms import MealPlanForm, MealRatingForm, RecipeForm
from .models import MealRating, Recipe


@login_required
def week_view(request):
    """Display the weekly meal plan grid."""
    today = date.today()
    # Sunday is first day of week
    start_date = today - timedelta(days=(today.weekday() + 1) % 7)

    meal_plans = services.get_meals_for_week(start_date)
    meal_plans_by_date = {mp.date: mp for mp in meal_plans}

    # Build list of days with their meal plans
    days = []
    for i in range(7):
        day_date = start_date + timedelta(days=i)
        days.append({
            "date": day_date,
            "meal_plan": meal_plans_by_date.get(day_date),
        })

    return render(request, "meals/week.html", {
        "start_date": start_date,
        "end_date": start_date + timedelta(days=6),
        "days": days,
    })


@login_required
def meal_plan_detail(request, pk):
    """Display a single meal plan's details."""
    meal_plan = services.get_meal_plan(meal_plan_id=pk)
    if meal_plan is None:
        raise Http404("Meal plan not found")
    return render(request, "meals/meal_plan_detail.html", {"meal_plan": meal_plan})


@login_required
def meal_plan_create(request):
    """Create a new meal plan."""
    initial = {}
    # Pre-fill date from querystring if provided
    date_str = request.GET.get("date")
    if date_str:
        try:
            initial["date"] = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    if request.method == "POST":
        form = MealPlanForm(request.POST)
        if form.is_valid():
            meal_plan = form.save(commit=False)
            meal_plan.created_by = request.user
            meal_plan.save()
            return redirect("meals:meal_plan_detail", pk=meal_plan.id)
    else:
        form = MealPlanForm(initial=initial)

    return render(request, "meals/meal_plan_form.html", {
        "form": form,
        "title": "Add Meal Plan",
        "submit_label": "Create Meal Plan",
        "combos": services.get_qualified_combos(active_only=True, min_rating=3),
    })


@login_required
def meal_plan_edit(request, pk):
    """Edit an existing meal plan (household-wide access)."""
    meal_plan = services.get_meal_plan(meal_plan_id=pk)
    if meal_plan is None:
        raise Http404("Meal plan not found")

    # Prevent edits if finalized
    if meal_plan.status == "FINALIZED":
        messages.warning(request, "This meal plan is finalized. Unfinalize it to make changes.")
        return redirect("meals:meal_plan_detail", pk=pk)

    if request.method == "POST":
        form = MealPlanForm(request.POST, instance=meal_plan)
        if form.is_valid():
            saved_plan = form.save(commit=False)
            # Check if finalize button was clicked
            if request.POST.get("finalize"):
                saved_plan.status = "FINALIZED"
                messages.success(request, "Meal plan saved and finalized.")
            saved_plan.save()
            return redirect("meals:week")
    else:
        form = MealPlanForm(instance=meal_plan)

    return render(request, "meals/meal_plan_form.html", {
        "form": form,
        "meal_plan": meal_plan,
        "title": "Pick Recipes",
        "submit_label": "Save",
        "combos": services.get_qualified_combos(active_only=True, min_rating=3),
        "top_combo": services.suggest_top_combo(),
    })


@login_required
def meal_plan_pick(request, date_str):
    """Get or create a MealPlan for the given date and redirect to edit."""
    try:
        plan_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise Http404("Invalid date format")

    meal_plan, created = services.get_or_create_meal_plan(plan_date, request.user)

    return redirect("meals:meal_plan_edit", pk=meal_plan.id)


@login_required
def meal_plan_finalize(request, pk):
    """Set meal plan status to FINALIZED (household-wide access)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    meal_plan = services.get_meal_plan(meal_plan_id=pk)
    if meal_plan is None:
        raise Http404("Meal plan not found")

    services.finalize_meal_plan(meal_plan)
    messages.success(request, "Meal plan finalized.")
    return redirect("meals:week")


@login_required
def meal_plan_unfinalize(request, pk):
    """Set meal plan status back to DRAFT (household-wide access)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    meal_plan = services.get_meal_plan(meal_plan_id=pk)
    if meal_plan is None:
        raise Http404("Meal plan not found")

    services.unfinalize_meal_plan(meal_plan)
    messages.success(request, "Meal plan unfinalized. You can now edit it.")
    return redirect("meals:meal_plan_edit", pk=pk)


@login_required
def meal_plan_rate(request, pk):
    """Create or update a rating for a meal plan (household-wide access)."""
    meal_plan = services.get_meal_plan(meal_plan_id=pk)
    if meal_plan is None:
        raise Http404("Meal plan not found")

    # Get existing rating or None
    try:
        rating = meal_plan.rating
    except MealRating.DoesNotExist:
        rating = None

    if request.method == "POST":
        form = MealRatingForm(request.POST, instance=rating)
        if form.is_valid():
            meal_rating = form.save(commit=False)
            meal_rating.meal_plan = meal_plan
            meal_rating.save()
            messages.success(request, "Rating saved.")
            return redirect("meals:meal_plan_detail", pk=pk)
    else:
        form = MealRatingForm(instance=rating)

    return render(request, "meals/meal_plan_rate.html", {
        "form": form,
        "meal_plan": meal_plan,
        "existing_rating": rating,
    })


@login_required
def pick_top_combo(request, pk):
    """Quick-action: fill a meal plan with the best combo not used recently."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    meal_plan = services.get_meal_plan(meal_plan_id=pk)
    if meal_plan is None:
        raise Http404("Meal plan not found")

    if meal_plan.status == "FINALIZED":
        messages.warning(request, "This meal plan is finalized.")
        return redirect("meals:meal_plan_detail", pk=pk)

    combo = services.suggest_top_combo()
    if combo is None:
        messages.info(request, "No combo available — all top combos were used recently.")
        return redirect("meals:meal_plan_edit", pk=pk)

    meal_plan.main_recipe = combo.main_recipe
    meal_plan.side_recipe = combo.side_recipe
    meal_plan.save()

    messages.success(request, f"Picked top combo: {combo}")
    return redirect("meals:meal_plan_edit", pk=pk)


@login_required
def combo_list(request):
    """List qualified combos sorted by best-performing first."""
    show_all = request.GET.get("show_all") == "1"
    include_archived = request.GET.get("include_archived") == "1"
    min_rating = None if show_all else 3
    combos = services.get_qualified_combos(
        min_rating=min_rating,
        exclude_archived=not include_archived,
    )
    return render(request, "meals/combos.html", {
        "combos": combos,
        "show_all": show_all,
        "include_archived": include_archived,
    })


@login_required
def combo_detail(request, pk):
    """Show combo stats and historical rated meal plans."""
    combo = services.get_combo(pk)
    if combo is None:
        raise Http404("Combo not found")
    meal_plans = combo.rated_meal_plans().order_by("-date").prefetch_related("rating")
    return render(request, "meals/combo_detail.html", {
        "combo": combo,
        "meal_plans": meal_plans,
    })


@login_required
def combo_toggle_archive(request, pk):
    """Toggle a combo's archived state (POST only)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    combo = services.get_combo(pk)
    if combo is None:
        raise Http404("Combo not found")

    services.toggle_combo_archived(combo)
    action = "archived" if combo.archived else "unarchived"
    messages.success(request, f"Combo {action}.")
    return redirect("meals:combo_detail", pk=pk)


@login_required
def ratings_history(request):
    """List past finalized meals with their ratings."""
    # Parse filters from query params
    rating_filter = request.GET.get("rating")
    would_repeat = request.GET.get("would_repeat")
    recipe_search = request.GET.get("recipe", "").strip()

    # Convert filters to appropriate types
    rating_value = int(rating_filter) if rating_filter and rating_filter.isdigit() else None
    would_repeat_value = None
    if would_repeat == "1":
        would_repeat_value = True
    elif would_repeat == "0":
        would_repeat_value = False

    # Get filtered meal plans via service
    meal_plans = services.get_rated_meal_plans(
        rating=rating_value,
        would_repeat=would_repeat_value,
        recipe_search=recipe_search or None,
    )

    return render(request, "meals/ratings_history.html", {
        "meal_plans": meal_plans,
        "filter_rating": rating_filter,
        "filter_would_repeat": would_repeat,
        "filter_recipe": recipe_search,
    })


@login_required
def recipe_list(request):
    """List all recipes with optional filters."""
    recipes = Recipe.objects.all().order_by("name")

    # Filter by kind
    kind = request.GET.get("kind")
    if kind in ("MAIN", "SIDE"):
        recipes = recipes.filter(kind=kind)

    # Filter by active status
    active = request.GET.get("active")
    if active == "1":
        recipes = recipes.filter(active=True)
    elif active == "0":
        recipes = recipes.filter(active=False)

    return render(request, "meals/recipe_list.html", {
        "recipes": recipes,
        "filter_kind": kind,
        "filter_active": active,
    })


@login_required
def recipe_create(request):
    """Create a new recipe."""
    if request.method == "POST":
        form = RecipeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Recipe created.")
            return redirect("meals:recipe_list")
    else:
        form = RecipeForm()

    return render(request, "meals/recipe_form.html", {
        "form": form,
        "title": "Add Recipe",
        "submit_label": "Create Recipe",
    })


@login_required
def recipe_edit(request, pk):
    """Edit an existing recipe."""
    try:
        recipe = Recipe.objects.get(pk=pk)
    except Recipe.DoesNotExist:
        raise Http404("Recipe not found")

    if request.method == "POST":
        form = RecipeForm(request.POST, instance=recipe)
        if form.is_valid():
            form.save()
            messages.success(request, "Recipe updated.")
            return redirect("meals:recipe_list")
    else:
        form = RecipeForm(instance=recipe)

    return render(request, "meals/recipe_form.html", {
        "form": form,
        "recipe": recipe,
        "title": "Edit Recipe",
        "submit_label": "Save Changes",
    })
