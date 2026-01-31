from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("", views.index, name="index"),
    path("today/", views.today, name="today"),
    path("today/assign/", views.today_assign, name="today_assign"),
    path("today/complete/", views.today_complete, name="today_complete"),
    path("today/uncomplete/", views.today_uncomplete, name="today_uncomplete"),
    path("domains/", views.domains, name="domains"),
    path("projects/", views.projects, name="projects"),
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/<int:task_id>/schedule/", views.schedule_edit, name="schedule_edit"),
    path("tasks/<int:task_id>/schedule/delete/", views.schedule_delete, name="schedule_delete"),
    path("analytics/", views.analytics, name="analytics"),
]
