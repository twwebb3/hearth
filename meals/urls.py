from django.urls import path

from . import views

app_name = "meals"

urlpatterns = [
    path("", views.week_view, name="week"),
    path("meal/<int:pk>/", views.meal_detail, name="meal_detail"),
    path("meal/create/", views.meal_create, name="meal_create"),
    path("meal/<int:pk>/edit/", views.meal_edit, name="meal_edit"),
    path("meal/<int:meal_pk>/ingredient/add/", views.ingredient_add, name="ingredient_add"),
    path("ingredient/<int:pk>/toggle/", views.ingredient_toggle, name="ingredient_toggle"),
]
