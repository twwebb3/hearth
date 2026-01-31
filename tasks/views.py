import datetime
import statistics
from collections import defaultdict

from django.db.models import Avg, Case, Count, F, Max, Q, Value, When
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


@require_POST
def reorder(request, pk):
    instance = get_object_or_404(TaskInstance, pk=pk)
    direction = request.POST.get("direction", "")

    if instance.status != TaskInstance.Status.INCOMPLETE:
        return redirect("tasks:today")

    siblings = list(
        TaskInstance.objects
        .filter(
            instance_date=instance.instance_date,
            status=TaskInstance.Status.INCOMPLETE,
        )
        .order_by("assigned_order", "task__priority")
    )

    pks = [s.pk for s in siblings]
    try:
        idx = pks.index(instance.pk)
    except ValueError:
        return redirect("tasks:today")

    if direction == "up" and idx > 0:
        swap_idx = idx - 1
    elif direction == "down" and idx < len(pks) - 1:
        swap_idx = idx + 1
    else:
        return redirect("tasks:today")

    other = siblings[swap_idx]
    instance.assigned_order, other.assigned_order = other.assigned_order, instance.assigned_order

    if instance.assigned_order == other.assigned_order:
        if direction == "up":
            instance.assigned_order -= 1
        else:
            instance.assigned_order += 1

    instance.save(update_fields=["assigned_order", "updated_at"])
    other.save(update_fields=["assigned_order", "updated_at"])

    return redirect("tasks:today")


_ALL_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
_DAY_LABELS = [
    ("MO", "Mon"), ("TU", "Tue"), ("WE", "Wed"), ("TH", "Thu"),
    ("FR", "Fri"), ("SA", "Sat"), ("SU", "Sun"),
]
_WEEKDAY_SET = {"MO", "TU", "WE", "TH", "FR"}
_WEEKEND_SET = {"SA", "SU"}


def _parse_rrule_to_ui(rrule_text):
    """Return (pattern, selected_days) for the schedule form."""
    if not rrule_text:
        return "daily", []
    upper = rrule_text.upper()
    if upper == "FREQ=DAILY":
        return "daily", []
    byday = []
    for part in upper.split(";"):
        if part.startswith("BYDAY="):
            byday = [d.strip() for d in part[6:].split(",") if d.strip()]
    if not byday:
        return "daily", []
    byday_set = set(byday)
    if byday_set == _WEEKDAY_SET:
        return "weekdays", list(_WEEKDAY_SET)
    if byday_set == _WEEKEND_SET:
        return "weekends", list(_WEEKEND_SET)
    return "custom", byday


def _build_rrule_from_ui(pattern, days):
    """Return an RRULE string from form selections."""
    if pattern == "weekdays":
        return "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    if pattern == "weekends":
        return "FREQ=WEEKLY;BYDAY=SA,SU"
    if pattern == "custom" and days:
        ordered = [d for d in _ALL_DAYS if d in days]
        return "FREQ=WEEKLY;BYDAY=" + ",".join(ordered)
    return "FREQ=DAILY"


def schedule_edit(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    rule = getattr(task, "schedule_rule", None)

    if request.method == "POST":
        pattern = request.POST.get("pattern", "daily")
        days = request.POST.getlist("days")
        start_date = request.POST.get("start_date", "").strip()
        end_date = request.POST.get("end_date", "").strip() or None
        tz = request.POST.get("timezone", "").strip() or "America/New_York"

        rrule = _build_rrule_from_ui(pattern, days)

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
        return redirect("tasks:task_detail", task_id=task_id)

    pattern, selected_days = _parse_rrule_to_ui(rule.rrule if rule else "")

    pattern_choices = [
        ("daily", "Every day"),
        ("weekdays", "Weekdays (Mon\u2013Fri)"),
        ("weekends", "Weekends (Sat\u2013Sun)"),
        ("custom", "Select days\u2026"),
    ]

    return render(request, "tasks/schedule_form.html", {
        "task": task,
        "rule": rule,
        "pattern": pattern,
        "pattern_choices": pattern_choices,
        "selected_days": selected_days,
        "day_labels": _DAY_LABELS,
    })


@require_POST
def schedule_toggle_pause(request, task_id):
    rule = get_object_or_404(TaskScheduleRule, task_id=task_id)
    rule.is_active = not rule.is_active
    rule.save(update_fields=["is_active", "updated_at"])
    return redirect("tasks:task_detail", task_id=task_id)


@require_POST
def schedule_delete(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    TaskScheduleRule.objects.filter(task=task).delete()
    return redirect("tasks:task_detail", task_id=task_id)


def domains(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            Domain.objects.create(
                name=name,
                description=request.POST.get("description", "").strip(),
                color_hex=request.POST.get("color_hex", "#6B7280").strip() or "#6B7280",
                sort_order=int(request.POST.get("sort_order", 0) or 0),
            )
        return redirect("tasks:domains")

    today_date = timezone.localdate()
    domain_list = (
        Domain.objects
        .annotate(
            active_projects=Count(
                "projects",
                filter=Q(projects__status=Project.Status.ACTIVE),
            ),
            todays_incomplete=(
                Count(
                    "projects__tasks__instances",
                    filter=Q(
                        projects__tasks__instances__instance_date=today_date,
                        projects__tasks__instances__status=TaskInstance.Status.INCOMPLETE,
                    ),
                )
                + Count(
                    "tasks__instances",
                    filter=Q(
                        tasks__instances__instance_date=today_date,
                        tasks__instances__status=TaskInstance.Status.INCOMPLETE,
                    ),
                )
            ),
        )
        .order_by("sort_order", "name")
    )
    return render(request, "tasks/domains.html", {
        "domains": domain_list,
        "date": today_date,
    })


def domain_detail(request, pk):
    domain = get_object_or_404(Domain, pk=pk)

    project_list = (
        Project.objects
        .filter(domain=domain)
        .annotate(
            active_tasks=Count("tasks", filter=Q(tasks__is_active=True)),
        )
        .order_by("name")
    )

    domain_tasks = (
        Task.objects
        .filter(domain=domain, is_active=True)
        .select_related("schedule_rule")
        .order_by("priority", "sort_order", "name")
    )

    return render(request, "tasks/domain_detail.html", {
        "domain": domain,
        "projects": project_list,
        "domain_tasks": domain_tasks,
    })


@require_POST
def domain_add_task(request, pk):
    domain = get_object_or_404(Domain, pk=pk)
    name = request.POST.get("name", "").strip()
    project_id = request.POST.get("project_id", "").strip()

    if not name:
        return redirect("tasks:domain_detail", pk=pk)

    if project_id:
        project = get_object_or_404(Project, pk=project_id, domain=domain)
        Task.objects.create(name=name, project=project)
    else:
        Task.objects.create(name=name, domain=domain)

    return redirect("tasks:domain_detail", pk=pk)


def projects(request):
    project_list = (
        Project.objects
        .select_related("domain")
        .annotate(
            active_tasks=Count("tasks", filter=Q(tasks__is_active=True)),
        )
        .order_by("domain__sort_order", "domain__name", "name")
    )
    return render(request, "tasks/projects.html", {
        "projects": project_list,
    })


def project_detail(request, pk):
    project = get_object_or_404(
        Project.objects.select_related("domain"), pk=pk,
    )
    today_date = timezone.localdate()

    tasks = (
        Task.objects
        .filter(project=project, is_active=True)
        .select_related("schedule_rule")
        .order_by("priority", "sort_order", "name")
    )

    upcoming = (
        Task.objects
        .filter(project=project, is_active=True, due_date__gte=today_date)
        .order_by("due_date", "priority", "name")
    )

    start_14 = today_date - datetime.timedelta(days=14)
    stats = (
        TaskInstance.objects
        .filter(
            task__project=project,
            instance_date__gte=start_14,
            instance_date__lte=today_date,
        )
        .aggregate(
            total=Count("pk"),
            completed=Count("pk", filter=Q(status=TaskInstance.Status.COMPLETE)),
            incomplete=Count("pk", filter=Q(status=TaskInstance.Status.INCOMPLETE)),
            skipped=Count("pk", filter=Q(status=TaskInstance.Status.SKIPPED)),
        )
    )
    total = stats["total"] or 0
    stats["rate"] = round(stats["completed"] / total * 100) if total else 0

    return render(request, "tasks/project_detail.html", {
        "project": project,
        "tasks": tasks,
        "upcoming": upcoming,
        "stats": stats,
        "start_14": start_14,
        "today_date": today_date,
    })


@require_POST
def project_add_task(request, pk):
    project = get_object_or_404(Project, pk=pk)
    name = request.POST.get("name", "").strip()
    due_date = request.POST.get("due_date", "").strip() or None

    if name:
        Task.objects.create(name=name, project=project, due_date=due_date)

    return redirect("tasks:project_detail", pk=pk)


def task_list(request):
    tasks = (
        Task.objects
        .select_related("project__domain", "domain")
        .order_by("is_active", "priority", "sort_order", "name")
    )
    return render(request, "tasks/task_list.html", {
        "tasks": tasks,
    })


def task_detail(request, task_id):
    task = get_object_or_404(
        Task.objects.select_related("project__domain", "domain"),
        pk=task_id,
    )
    today_date = timezone.localdate()
    start_14 = today_date - datetime.timedelta(days=14)

    rule = getattr(task, "schedule_rule", None)

    recent_instances = (
        TaskInstance.objects
        .filter(task=task, instance_date__gte=start_14)
        .order_by("-instance_date")
    )

    on_today = TaskInstance.objects.filter(
        task=task, instance_date=today_date,
    ).exists()

    return render(request, "tasks/task_detail.html", {
        "task": task,
        "rule": rule,
        "recent_instances": recent_instances,
        "on_today": on_today,
        "today_date": today_date,
    })


@require_POST
def task_deactivate(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    task.is_active = not task.is_active
    task.save(update_fields=["is_active", "updated_at"])
    return redirect("tasks:task_detail", task_id=task_id)


@require_POST
def task_add_to_today(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    today_date = timezone.localdate()
    next_order = _next_assigned_order(today_date)
    TaskInstance.objects.get_or_create(
        task=task,
        instance_date=today_date,
        defaults={
            "source": TaskInstance.Source.MANUAL,
            "assigned_order": next_order,
        },
    )
    return redirect("tasks:task_detail", task_id=task_id)


def _parse_date(value, fallback):
    if value:
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            pass
    return fallback


def _domain_rates_for_window(start, end):
    """Return {domain_pk: {total, completed}} for a date window."""
    date_via_project = Q(
        projects__tasks__instances__instance_date__gte=start,
        projects__tasks__instances__instance_date__lte=end,
    )
    date_via_direct = Q(
        tasks__instances__instance_date__gte=start,
        tasks__instances__instance_date__lte=end,
    )

    def _count(extra_q=Q()):
        return (
            Count("projects__tasks__instances", filter=date_via_project & extra_q)
            + Count("tasks__instances", filter=date_via_direct & extra_q)
        )

    return {
        d.pk: {"total": d.total, "completed": d.completed}
        for d in (
            Domain.objects
            .filter(date_via_project | date_via_direct)
            .annotate(
                total=_count(),
                completed=_count(
                    Q(projects__tasks__instances__status="complete")
                    | Q(tasks__instances__status="complete")
                ),
            )
            .filter(total__gt=0)
        )
    }


def analytics(request):
    today_date = timezone.localdate()
    start = _parse_date(request.GET.get("start"), today_date - datetime.timedelta(days=30))
    end = _parse_date(request.GET.get("end"), today_date)

    # --- 1. Domain completion rates across 7 / 14 / 30 day windows ---
    windows = [
        ("7d", 7),
        ("14d", 14),
        ("30d", 30),
    ]
    window_rates = {}
    all_domain_pks = set()
    for label, days in windows:
        w_start = today_date - datetime.timedelta(days=days)
        rates = _domain_rates_for_window(w_start, today_date)
        window_rates[label] = rates
        all_domain_pks |= rates.keys()

    domains_by_pk = {
        d.pk: d
        for d in Domain.objects.filter(pk__in=all_domain_pks)
    }

    domain_rows = []
    for pk in all_domain_pks:
        row = {"domain": domains_by_pk[pk]}
        for label, _ in windows:
            r = window_rates[label].get(pk, {"total": 0, "completed": 0})
            total = r["total"]
            completed = r["completed"]
            row[f"total_{label}"] = total
            row[f"completed_{label}"] = completed
            row[f"rate_{label}"] = round(completed / total * 100) if total else 0
        domain_rows.append(row)

    domain_rows.sort(key=lambda r: r["rate_30d"], reverse=True)

    # --- 1b. Activity timeline (rolling 30 days) ---
    start_30 = today_date - datetime.timedelta(days=30)

    completion_rows = (
        TaskInstance.objects
        .filter(
            status=TaskInstance.Status.COMPLETE,
            completed_at__isnull=False,
            instance_date__gte=start_30,
            instance_date__lte=today_date,
        )
        .values_list("instance_date", "completed_at")
    )

    by_date = defaultdict(list)
    all_minutes = []
    for inst_date, completed_at in completion_rows:
        local_dt = timezone.localtime(completed_at)
        mins = local_dt.hour * 60 + local_dt.minute
        by_date[inst_date].append(mins)
        all_minutes.append(mins)

    timeline = []
    for day_offset in range(31):
        d = start_30 + datetime.timedelta(days=day_offset)
        mins_list = by_date.get(d, [])
        count = len(mins_list)
        if mins_list:
            med = statistics.median(mins_list)
            median_time = f"{int(med) // 60:02d}:{int(med) % 60:02d}"
        else:
            median_time = None
        timeline.append({"date": d, "count": count, "median_time": median_time})

    max_timeline = max((r["count"] for r in timeline), default=0)
    for r in timeline:
        r["bar_pct"] = round(r["count"] / max_timeline * 100) if max_timeline else 0

    total_completions = sum(r["count"] for r in timeline)
    days_with = sum(1 for r in timeline if r["count"])
    avg_per_day = round(total_completions / days_with, 1) if days_with else 0
    if all_minutes:
        overall_med = statistics.median(all_minutes)
        overall_median_time = f"{int(overall_med) // 60:02d}:{int(overall_med) % 60:02d}"
    else:
        overall_median_time = None

    # --- 2. Task consistency (rolling 30 days) ---
    date_q = Q(
        instances__instance_date__gte=start_30,
        instances__instance_date__lte=today_date,
    )

    task_consistency = list(
        Task.objects
        .filter(is_active=True)
        .annotate(
            total_count=Count("instances", filter=date_q),
            completed_count=Count(
                "instances",
                filter=date_q & Q(instances__status="complete"),
            ),
            avg_completion_order=Avg(
                "instances__completion_order",
                filter=date_q & Q(instances__status="complete"),
            ),
        )
        .filter(total_count__gte=3)
        .select_related("project__domain", "domain")
    )

    for t in task_consistency:
        t.rate = round(t.completed_count / t.total_count * 100)
        t.avg_order_display = (
            round(t.avg_completion_order, 1)
            if t.avg_completion_order is not None else None
        )

    consistently_completed = sorted(
        [t for t in task_consistency if t.rate >= 80],
        key=lambda t: (-t.rate, t.name),
    )
    consistently_incomplete = sorted(
        [t for t in task_consistency if t.rate <= 50],
        key=lambda t: (t.rate, t.name),
    )

    # --- 3. Completion by project (custom date range) ---
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

    # --- 3. Chronic incompletion (custom date range) ---
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

    # --- 5. Overdue aging ---
    overdue_instances = list(
        TaskInstance.objects
        .filter(
            task__due_date__isnull=False,
            status=TaskInstance.Status.INCOMPLETE,
        )
        .filter(instance_date__gt=F("task__due_date"))
        .select_related("task__project__domain", "task__domain")
        .order_by("task__due_date", "-instance_date")
    )

    for inst in overdue_instances:
        inst.days_overdue = (inst.instance_date - inst.task.due_date).days

    # Deduplicated list: one row per task, keeping the most-overdue instance.
    seen_tasks = set()
    overdue_list = []
    for inst in sorted(overdue_instances, key=lambda i: -i.days_overdue):
        if inst.task_id not in seen_tasks:
            seen_tasks.add(inst.task_id)
            overdue_list.append(inst)

    # Histogram buckets.
    aging_buckets = [
        ("1\u20133 days", 1, 3),
        ("4\u20137 days", 4, 7),
        ("8\u201314 days", 8, 14),
        ("15\u201330 days", 15, 30),
        ("30+ days", 31, None),
    ]
    histogram = []
    for label, lo, hi in aging_buckets:
        count = sum(
            1 for inst in overdue_instances
            if inst.days_overdue >= lo and (hi is None or inst.days_overdue <= hi)
        )
        histogram.append({"label": label, "count": count})

    max_bucket = max((b["count"] for b in histogram), default=0)
    for b in histogram:
        b["bar_pct"] = round(b["count"] / max_bucket * 100) if max_bucket else 0

    return render(request, "tasks/analytics.html", {
        "start": start,
        "end": end,
        "domain_rows": domain_rows,
        "timeline": timeline,
        "total_completions": total_completions,
        "avg_per_day": avg_per_day,
        "overall_median_time": overall_median_time,
        "consistently_completed": consistently_completed,
        "consistently_incomplete": consistently_incomplete,
        "by_project": by_project,
        "chronic": chronic,
        "overdue_list": overdue_list,
        "histogram": histogram,
    })
