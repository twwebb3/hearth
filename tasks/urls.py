from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("", views.index, name="index"),
    path("today/", views.today, name="today"),
    path("today/assign/", views.today_assign, name="today_assign"),
    path("today/add/", views.today_add, name="today_add"),
    path("today/complete/", views.today_complete, name="today_complete"),
    path("today/uncomplete/", views.today_uncomplete, name="today_uncomplete"),
    path("instances/<int:pk>/toggle-complete/", views.toggle_complete, name="toggle_complete"),
    path("instances/<int:pk>/reorder/", views.reorder, name="reorder"),
    path("domains/", views.domains, name="domains"),
    path("domains/<int:pk>/", views.domain_detail, name="domain_detail"),
    path("domains/<int:pk>/delete/", views.domain_delete, name="domain_delete"),
    path("domains/<int:pk>/add-task/", views.domain_add_task, name="domain_add_task"),
    path("projects/", views.projects, name="projects"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/delete/", views.project_delete, name="project_delete"),
    path("projects/<int:pk>/add-task/", views.project_add_task, name="project_add_task"),
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/<int:task_id>/", views.task_detail, name="task_detail"),
    path("tasks/<int:task_id>/deactivate/", views.task_deactivate, name="task_deactivate"),
    path("tasks/<int:task_id>/add-to-today/", views.task_add_to_today, name="task_add_to_today"),
    path("tasks/<int:task_id>/schedule/", views.schedule_edit, name="schedule_edit"),
    path("tasks/<int:task_id>/schedule/toggle-pause/", views.schedule_toggle_pause, name="schedule_toggle_pause"),
    path("tasks/<int:task_id>/schedule/delete/", views.schedule_delete, name="schedule_delete"),
    path("analytics/", views.analytics, name="analytics"),
]
