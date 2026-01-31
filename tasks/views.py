import datetime

from django.db.models import Case, Count, Max, Q, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Domain, Project, Task, TaskExecution, TaskInstance, TaskScheduleRule
from .services import generate_instances_for_date, rollover_incomplete


def index(request):
    return render(request, "tasks/index.html")


def _instances_for_date(target_date):
    """Return today's instances annotated with dot_color, split into
    (incomplete, completed) querysets."""
    base = (
        TaskInstance.objects
        .filter(instance_date=target_date)
        .select_related("task__project__domain", "task__domain")
        .annotate(
            dot_color=Coalesce(
                Case(
                    When(task__project__color_hex="", then=None),
                    default="task__project__color_hex",
                ),
                "task__project__domain__color_hex",
                "task__domain__color_hex",
            ),
        )
    )
    incomplete = (
        base
        .filter(status=TaskInstance.Status.INCOMPLETE)
        .order_by("assigned_order", "task__priority")
    )
    completed = (
        base
        .filter(status__in=[TaskInstance.Status.COMPLETE, TaskInstance.Status.SKIPPED])
        .annotate(
            status_rank=Case(
                When(status="complete", then=Value(0)),
                When(status="skipped", then=Value(1)),
                default=Value(2),
            ),
        )
        .order_by("status_rank", "completion_order")
    )
    return incomplete, completed


def _next_assigned_order(target_date):
    max_order = (
        TaskInstance.objects
        .filter(instance_date=target_date)
        .aggregate(m=Max("assigned_order"))["m"]
    )
    return (max_order if max_order is not None else -1) + 1


def today(request):
    today_date = timezone.localdate()
    yesterday = today_date - datetime.timedelta(days=1)

    # Ensure scheduled + rolled-over instances exist (idempotent).
    generate_instances_for_date(today_date)
    rollover_incomplete(yesterday, today_date)

    incomplete, completed = _instances_for_date(today_date)

    # Tasks not already on today's list, for the "add existing" dropdown.
    already_on_today = TaskInstance.objects.filter(
        instance_date=today_date,
    ).values_list("task_id", flat=True)
    available_tasks = (
        Task.objects
        .filter(is_active=True)
        .exclude(pk__in=already_on_today)
        .select_related("project__domain", "domain")
        .order_by("name")
    )

    return render(request, "tasks/today.html", {
        "date": today_date,
        "incomplete": incomplete,
        "completed": completed,
        "available_tasks": available_tasks,
        "domains": Domain.objects.all(),
    })


@require_POST
def today_assign(request):
    task = get_object_or_404(Task, pk=request.POST.get("task_id"))
    assigned_order = request.POST.get("assigned_order")
    defaults = {"source": TaskInstance.Source.MANUAL}
    if assigned_order is not None and assigned_order != "":
        defaults["assigned_order"] = int(assigned_order)
    TaskInstance.objects.get_or_create(
        task=task,
        instance_date=timezone.localdate(),
        defaults=defaults,
    )
    return redirect("tasks:today")


@require_POST
def today_add(request):
    today_date = timezone.localdate()
    task_id = request.POST.get("task_id", "").strip()
    new_name = request.POST.get("new_name", "").strip()
    domain_id = request.POST.get("domain_id", "").strip()

    if task_id:
        # Existing task
        task = get_object_or_404(Task, pk=task_id)
    elif new_name and domain_id:
        # Create a new task under the chosen domain
        domain = get_object_or_404(Domain, pk=domain_id)
        task = Task.objects.create(name=new_name, domain=domain)
    else:
        return redirect("tasks:today")

    next_order = _next_assigned_order(today_date)
    TaskInstance.objects.get_or_create(
        task=task,
        instance_date=today_date,
        defaults={
            "source": TaskInstance.Source.MANUAL,
            "assigned_order": next_order,
        },
    )
    return redirect("tasks:today")


@require_POST
def today_complete(request):
    instance = get_object_or_404(
        TaskInstance, pk=request.POST.get("task_instance_id")
    )
    max_order = (
        TaskInstance.objects
        .filter(instance_date=instance.instance_date, status=TaskInstance.Status.COMPLETE)
        .aggregate(m=Max("completion_order"))["m"]
    )
    next_order = (max_order or 0) + 1
    instance.status = TaskInstance.Status.COMPLETE
    instance.completion_order = next_order
    instance.completed_at = timezone.now()
    instance.skipped_at = None
    instance.save(update_fields=["status", "completion_order", "completed_at", "skipped_at", "updated_at"])
    TaskExecution.objects.create(
        task_instance=instance,
        event_type=TaskExecution.EventType.COMPLETED,
        performed_by=request.user if request.user.is_authenticated else None,
    )
    return redirect("tasks:today")


@require_POST
def today_uncomplete(request):
    instance = get_object_or_404(
        TaskInstance, pk=request.POST.get("task_instance_id")
    )
    instance.status = TaskInstance.Status.INCOMPLETE
    instance.completion_order = None
    instance.completed_at = None
    instance.skipped_at = None
    instance.save(update_fields=["status", "completion_order", "completed_at", "skipped_at", "updated_at"])
    TaskExecution.objects.create(
        task_instance=instance,
        event_type=TaskExecution.EventType.UNCOMPLETED,
        performed_by=request.user if request.user.is_authenticated else None,
    )
    return redirect("tasks:today")


@require_POST
def toggle_complete(request, pk):
    instance = get_object_or_404(TaskInstance, pk=pk)
    if instance.status == TaskInstance.Status.INCOMPLETE:
        max_order = (
            TaskInstance.objects
            .filter(instance_date=instance.instance_date, status=TaskInstance.Status.COMPLETE)
            .aggregate(m=Max("completion_order"))["m"]
        )
        instance.status = TaskInstance.Status.COMPLETE
        instance.completion_order = (max_order or 0) + 1
        instance.completed_at = timezone.now()
        instance.skipped_at = None
        event_type = TaskExecution.EventType.COMPLETED
    else:
        instance.status = TaskInstance.Status.INCOMPLETE
        instance.completion_order = None
        instance.completed_at = None
        instance.skipped_at = None
        event_type = TaskExecution.EventType.UNCOMPLETED
    instance.save(update_fields=[
        "status", "completion_order", "completed_at", "skipped_at", "updated_at",
    ])
    TaskExecution.objects.create(
        task_instance=instance,
        event_type=event_type,
        performed_by=request.user if request.user.is_authenticated else None,
    )
    return redirect("tasks:today")


def schedule_edit(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    rule = getattr(task, "schedule_rule", None)

    if request.method == "POST":
        rrule = request.POST.get("rrule", "").strip()
        start_date = request.POST.get("start_date", "").strip()
        end_date = request.POST.get("end_date", "").strip() or None
        tz = request.POST.get("timezone", "").strip() or "America/New_York"

        if rule:
            rule.rrule = rrule
            rule.start_date = start_date
            rule.end_date = end_date
            rule.timezone = tz
            rule.save()
        else:
            TaskScheduleRule.objects.create(
                task=task,
                rrule=rrule,
                start_date=start_date,
                end_date=end_date,
                timezone=tz,
            )
        return redirect("tasks:task_list")

    return render(request, "tasks/schedule_form.html", {
        "task": task,
        "rule": rule,
    })


@require_POST
def schedule_delete(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    TaskScheduleRule.objects.filter(task=task).delete()
    return redirect("tasks:task_list")


def domains(request):
    return render(request, "tasks/domains.html")


def projects(request):
    return render(request, "tasks/projects.html")


def task_list(request):
    return render(request, "tasks/task_list.html")


def _parse_date(value, fallback):
    if value:
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            pass
    return fallback


def analytics(request):
    today_date = timezone.localdate()
    start = _parse_date(request.GET.get("start"), today_date - datetime.timedelta(days=30))
    end = _parse_date(request.GET.get("end"), today_date)

    date_filter = Q(
        instances__instance_date__gte=start,
        instances__instance_date__lte=end,
    )
    complete_q = Q(instances__status="complete") & Q(
        instances__instance_date__gte=start,
        instances__instance_date__lte=end,
    )
    incomplete_q = Q(instances__status="incomplete") & Q(
        instances__instance_date__gte=start,
        instances__instance_date__lte=end,
    )
    skipped_q = Q(instances__status="skipped") & Q(
        instances__instance_date__gte=start,
        instances__instance_date__lte=end,
    )

    # --- 1. Completion by domain ---
    # Instances reach a domain via two paths:
    #   projects__tasks__instances  (task under a project)
    #   tasks__instances            (task directly under domain)
    date_via_project = Q(
        projects__tasks__instances__instance_date__gte=start,
        projects__tasks__instances__instance_date__lte=end,
    )
    date_via_direct = Q(
        tasks__instances__instance_date__gte=start,
        tasks__instances__instance_date__lte=end,
    )

    def _domain_count(extra_q=Q()):
        """Count distinct instances for a domain across both paths."""
        return (
            Count(
                "projects__tasks__instances",
                filter=date_via_project & extra_q,
            )
            + Count(
                "tasks__instances",
                filter=date_via_direct & extra_q,
            )
        )

    by_domain = (
        Domain.objects
        .filter(date_via_project | date_via_direct)
        .annotate(
            total=_domain_count(),
            completed=_domain_count(Q(
                projects__tasks__instances__status="complete",
            ) | Q(
                tasks__instances__status="complete",
            )),
            incomplete=_domain_count(Q(
                projects__tasks__instances__status="incomplete",
            ) | Q(
                tasks__instances__status="incomplete",
            )),
            skipped=_domain_count(Q(
                projects__tasks__instances__status="skipped",
            ) | Q(
                tasks__instances__status="skipped",
            )),
        )
        .filter(total__gt=0)
        .order_by("-completed", "name")
    )

    # --- 2. Completion by project ---
    by_project = (
        Project.objects
        .filter(tasks__instances__instance_date__gte=start,
                tasks__instances__instance_date__lte=end)
        .select_related("domain")
        .annotate(
            total=Count(
                "tasks__instances",
                filter=Q(
                    tasks__instances__instance_date__gte=start,
                    tasks__instances__instance_date__lte=end,
                ),
            ),
            completed=Count(
                "tasks__instances",
                filter=Q(
                    tasks__instances__status="complete",
                    tasks__instances__instance_date__gte=start,
                    tasks__instances__instance_date__lte=end,
                ),
            ),
            incomplete=Count(
                "tasks__instances",
                filter=Q(
                    tasks__instances__status="incomplete",
                    tasks__instances__instance_date__gte=start,
                    tasks__instances__instance_date__lte=end,
                ),
            ),
            skipped=Count(
                "tasks__instances",
                filter=Q(
                    tasks__instances__status="skipped",
                    tasks__instances__instance_date__gte=start,
                    tasks__instances__instance_date__lte=end,
                ),
            ),
        )
        .filter(total__gt=0)
        .order_by("-completed", "name")
    )

    # --- 3. Chronic incompletion (appearances >= 5, still incomplete) ---
    chronic = (
        Task.objects
        .annotate(
            incomplete_count=Count(
                "instances",
                filter=Q(
                    instances__status="incomplete",
                    instances__instance_date__gte=start,
                    instances__instance_date__lte=end,
                ),
            ),
            total_count=Count(
                "instances",
                filter=Q(
                    instances__instance_date__gte=start,
                    instances__instance_date__lte=end,
                ),
            ),
        )
        .filter(incomplete_count__gte=5)
        .select_related("project__domain", "domain")
        .order_by("-incomplete_count")
    )

    return render(request, "tasks/analytics.html", {
        "start": start,
        "end": end,
        "by_domain": by_domain,
        "by_project": by_project,
        "chronic": chronic,
    })
