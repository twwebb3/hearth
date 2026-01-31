"""Service helpers for the tasks app."""

from .models import TaskInstance, TaskScheduleRule

RRULE_DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _parse_rrule(rrule_str):
    """Parse a minimal RRULE string into a dict of its parts.

    Supports FREQ=DAILY and FREQ=WEEKLY;BYDAY=MO,TU,...
    """
    parts = {}
    for token in rrule_str.strip().split(";"):
        key, _, value = token.partition("=")
        parts[key.strip().upper()] = value.strip().upper()
    return parts


def _rrule_matches_date(parts, date):
    """Return True if the parsed rrule applies to *date*."""
    freq = parts.get("FREQ")
    if freq == "DAILY":
        return True
    if freq == "WEEKLY":
        byday = parts.get("BYDAY", "")
        if not byday:
            return True  # every day of every week
        day_codes = [d.strip() for d in byday.split(",")]
        return date.weekday() in [
            RRULE_DAYS[code] for code in day_codes if code in RRULE_DAYS
        ]
    return False


def generate_instances_for_date(date):
    """Create TaskInstances for all active scheduled tasks that apply to *date*.

    Returns the list of TaskInstance objects that were created (not pre-existing).
    """
    rules = (
        TaskScheduleRule.objects
        .filter(
            task__is_active=True,
            start_date__lte=date,
        )
        .exclude(end_date__lt=date)
        .select_related("task")
    )

    created = []
    for rule in rules:
        parts = _parse_rrule(rule.rrule)
        if not _rrule_matches_date(parts, date):
            continue
        _, was_created = TaskInstance.objects.get_or_create(
            task=rule.task,
            instance_date=date,
            defaults={"source": TaskInstance.Source.GENERATED},
        )
        if was_created:
            created.append(rule.task)

    return created
