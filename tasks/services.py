"""Service helpers for the tasks app."""

import datetime

from django.db.models import Max
from dateutil.rrule import rrulestr

from .models import TaskInstance, TaskScheduleRule


def _rrule_includes_date(rrule_text, start_date, end_date, target_date):
    """Return True if the rrule produces *target_date* as an occurrence."""
    dtstart = datetime.datetime.combine(start_date, datetime.time.min)
    rule = rrulestr(f"RRULE:{rrule_text}", dtstart=dtstart)

    # Only check occurrences up to end_date (or target_date if no end).
    until = datetime.datetime.combine(
        end_date if end_date and end_date <= target_date else target_date,
        datetime.time.max,
    )

    target_dt = datetime.datetime.combine(target_date, datetime.time.min)
    # .between() returns occurrences in [after, before] inclusive.
    return len(rule.between(target_dt, target_dt, inc=True)) > 0 and target_dt <= until


def generate_instances_for_date(target_date):
    """Create TaskInstances for all active scheduled tasks that apply to *target_date*.

    Uses dateutil.rrule to evaluate arbitrary RRULE strings against the date.
    Returns the list of Task objects for which new instances were created.
    """
    rules = (
        TaskScheduleRule.objects
        .filter(
            is_active=True,
            task__is_active=True,
            start_date__lte=target_date,
        )
        .exclude(end_date__lt=target_date)
        .select_related("task")
        .order_by("task__priority", "task__sort_order")
    )

    # Collect matching tasks in priority/sort_order so we can assign
    # assigned_order sequentially.
    matching = []
    for rule in rules:
        if not _rrule_includes_date(
            rule.rrule, rule.start_date, rule.end_date, target_date,
        ):
            continue
        matching.append(rule.task)

    created = []
    for order, task in enumerate(matching):
        _, was_created = TaskInstance.objects.get_or_create(
            task=task,
            instance_date=target_date,
            defaults={
                "source": TaskInstance.Source.GENERATED,
                "assigned_order": order,
            },
        )
        if was_created:
            created.append(task)

    return created


def rollover_incomplete(from_date, to_date):
    """Copy yesterday's incomplete instances into today as ROLLED_OVER.

    Assigns assigned_order starting after the current max for *to_date*
    so rolled-over items appear after scheduled ones.
    Returns the list of TaskInstance objects that were created.
    """
    stale = (
        TaskInstance.objects
        .filter(
            instance_date=from_date,
            status=TaskInstance.Status.INCOMPLETE,
            task__is_active=True,
        )
        .select_related("task")
        .order_by("assigned_order", "task__priority", "task__sort_order")
    )

    if not stale.exists():
        return []

    max_order = (
        TaskInstance.objects
        .filter(instance_date=to_date)
        .aggregate(m=Max("assigned_order"))["m"]
    )
    next_order = (max_order if max_order is not None else -1) + 1

    created = []
    for inst in stale:
        _, was_created = TaskInstance.objects.get_or_create(
            task=inst.task,
            instance_date=to_date,
            defaults={
                "source": TaskInstance.Source.ROLLED_OVER,
                "assigned_order": next_order,
            },
        )
        if was_created:
            created.append(inst)
            next_order += 1

    return created
