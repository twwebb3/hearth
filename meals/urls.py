from django.urls import path

from . import views

app_name = "meals"

urlpatterns = [
    path("", views.week_view, name="week"),
    path("plan/<int:pk>/", views.meal_plan_detail, name="meal_plan_detail"),
    path("plan/create/", views.meal_plan_create, name="meal_plan_create"),
    path("plan/<int:pk>/edit/", views.meal_plan_edit, name="meal_plan_edit"),
    path("plan/pick/<str:date_str>/", views.meal_plan_pick, name="meal_plan_pick"),
    path("plan/<int:pk>/finalize/", views.meal_plan_finalize, name="meal_plan_finalize"),
    path("plan/<int:pk>/unfinalize/", views.meal_plan_unfinalize, name="meal_plan_unfinalize"),
    path("plan/<int:pk>/rate/", views.meal_plan_rate, name="meal_plan_rate"),
    path("plan/<int:pk>/pick-top-combo/", views.pick_top_combo, name="pick_top_combo"),
    path("history/", views.ratings_history, name="ratings_history"),
    path("combos/", views.combo_list, name="combo_list"),
    path("combos/<int:pk>/", views.combo_detail, name="combo_detail"),
    path("combos/<int:pk>/toggle-archive/", views.combo_toggle_archive, name="combo_toggle_archive"),
    # Recipe management
    path("recipes/", views.recipe_list, name="recipe_list"),
    path("recipes/create/", views.recipe_create, name="recipe_create"),
    path("recipes/<int:pk>/edit/", views.recipe_edit, name="recipe_edit"),
]
