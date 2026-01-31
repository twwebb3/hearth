import datetime

from django.db import IntegrityError
from django.test import TestCase, RequestFactory
from django.utils import timezone

from .models import (
    Domain, Project, Task, TaskExecution, TaskInstance, TaskScheduleRule,
)
from .services import generate_instances_for_date
from .views import today


def _make_task(name="Test task", domain_name="D", project_name="P",
               direct_domain=False, **kwargs):
    """Helper: create Domain -> Project -> Task in one call.

    If direct_domain=True, attach the task directly to the domain (no project).
    """
    domain = Domain.objects.create(name=domain_name, sort_order=0)
    if direct_domain:
        return Task.objects.create(name=name, domain=domain, **kwargs)
    project = Project.objects.create(name=project_name, domain=domain)
    return Task.objects.create(name=name, project=project, **kwargs)


class TaskOwnershipConstraintTests(TestCase):
    """Task must have exactly one of (project, domain)."""

    def test_project_only_ok(self):
        task = _make_task(name="Via project")
        self.assertIsNotNone(task.project)
        self.assertIsNone(task.domain)

    def test_domain_only_ok(self):
        task = _make_task(name="Via domain", direct_domain=True)
        self.assertIsNone(task.project)
        self.assertIsNotNone(task.domain)

    def test_both_set_raises(self):
        domain = Domain.objects.create(name="D", sort_order=0)
        project = Project.objects.create(name="P", domain=domain)
        with self.assertRaises(IntegrityError):
            Task.objects.create(name="Bad", project=project, domain=domain)

    def test_neither_set_raises(self):
        with self.assertRaises(IntegrityError):
            Task.objects.create(name="Orphan")

    def test_effective_domain_via_project(self):
        task = _make_task(name="Via project", domain_name="TestD")
        self.assertEqual(task.effective_domain.name, "TestD")

    def test_effective_domain_direct(self):
        task = _make_task(name="Direct", domain_name="TestD", direct_domain=True)
        self.assertEqual(task.effective_domain.name, "TestD")


class UniqueInstanceConstraintTests(TestCase):
    """The (task, instance_date) pair must be unique."""

    def test_duplicate_raises(self):
        task = _make_task()
        date = datetime.date(2026, 3, 1)
        TaskInstance.objects.create(task=task, instance_date=date)
        with self.assertRaises(IntegrityError):
            TaskInstance.objects.create(task=task, instance_date=date)

    def test_same_task_different_dates_ok(self):
        task = _make_task()
        TaskInstance.objects.create(task=task, instance_date=datetime.date(2026, 3, 1))
        TaskInstance.objects.create(task=task, instance_date=datetime.date(2026, 3, 2))
        self.assertEqual(TaskInstance.objects.filter(task=task).count(), 2)

    def test_same_date_different_tasks_ok(self):
        t1 = _make_task(name="A", domain_name="D1", project_name="P1")
        t2 = _make_task(name="B", domain_name="D2", project_name="P2")
        date = datetime.date(2026, 3, 1)
        TaskInstance.objects.create(task=t1, instance_date=date)
        TaskInstance.objects.create(task=t2, instance_date=date)
        self.assertEqual(TaskInstance.objects.filter(instance_date=date).count(), 2)


class GeneratorIdempotencyTests(TestCase):
    """generate_instances_for_date must be idempotent."""

    def setUp(self):
        self.task = _make_task(name="Daily chore")
        TaskScheduleRule.objects.create(
            task=self.task,
            rrule="FREQ=DAILY",
            start_date=datetime.date(2026, 1, 1),
        )
        self.date = datetime.date(2026, 6, 15)

    def test_first_run_creates(self):
        created = generate_instances_for_date(self.date)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0], self.task)
        self.assertTrue(
            TaskInstance.objects.filter(
                task=self.task, instance_date=self.date, source="generated",
            ).exists()
        )

    def test_second_run_creates_nothing(self):
        generate_instances_for_date(self.date)
        created = generate_instances_for_date(self.date)
        self.assertEqual(len(created), 0)
        self.assertEqual(
            TaskInstance.objects.filter(task=self.task, instance_date=self.date).count(),
            1,
        )

    def test_inactive_task_skipped(self):
        self.task.is_active = False
        self.task.save()
        created = generate_instances_for_date(self.date)
        self.assertEqual(len(created), 0)

    def test_weekly_byday_filtering(self):
        task2 = _make_task(name="MWF task", domain_name="D2", project_name="P2")
        TaskScheduleRule.objects.create(
            task=task2,
            rrule="FREQ=WEEKLY;BYDAY=MO,WE,FR",
            start_date=datetime.date(2026, 1, 1),
        )
        # 2026-06-15 is a Monday
        monday = datetime.date(2026, 6, 15)
        self.assertEqual(monday.weekday(), 0)
        created = generate_instances_for_date(monday)
        task_names = [t.name for t in created]
        self.assertIn("MWF task", task_names)

        # 2026-06-16 is a Tuesday — MWF task should NOT be generated
        tuesday = datetime.date(2026, 6, 16)
        created_tue = generate_instances_for_date(tuesday)
        task_names_tue = [t.name for t in created_tue]
        self.assertNotIn("MWF task", task_names_tue)

    def test_end_date_respected(self):
        self.task.schedule_rule.end_date = datetime.date(2026, 3, 1)
        self.task.schedule_rule.save()
        created = generate_instances_for_date(datetime.date(2026, 6, 15))
        self.assertEqual(len(created), 0)

    def test_manual_instance_blocks_generated_duplicate(self):
        """If a manual instance already exists, generator must not fail."""
        TaskInstance.objects.create(
            task=self.task, instance_date=self.date, source="manual",
        )
        created = generate_instances_for_date(self.date)
        self.assertEqual(len(created), 0)
        self.assertEqual(
            TaskInstance.objects.filter(task=self.task, instance_date=self.date).count(),
            1,
        )

    def test_assigned_order_from_priority_and_sort_order(self):
        """Generated instances get assigned_order based on task priority then sort_order."""
        domain = Domain.objects.create(name="OD", sort_order=0)
        # priority=0 sort_order=10 → should be first (order 0 or 1 depending on setUp task)
        t_high = Task.objects.create(
            name="High", domain=domain, priority=0, sort_order=10,
        )
        # priority=5 sort_order=1 → lower priority, should come after
        t_low = Task.objects.create(
            name="Low", domain=domain, priority=5, sort_order=1,
        )
        # priority=0 sort_order=20 → same priority as High but higher sort_order
        t_mid = Task.objects.create(
            name="Mid", domain=domain, priority=0, sort_order=20,
        )
        for t in (t_high, t_low, t_mid):
            TaskScheduleRule.objects.create(
                task=t, rrule="FREQ=DAILY",
                start_date=datetime.date(2026, 1, 1),
            )
        date = datetime.date(2026, 7, 1)
        generate_instances_for_date(date)

        orders = {
            inst.task.name: inst.assigned_order
            for inst in TaskInstance.objects.filter(
                instance_date=date, task__in=[t_high, t_low, t_mid],
            ).select_related("task")
        }
        self.assertLess(orders["High"], orders["Mid"])
        self.assertLess(orders["Mid"], orders["Low"])


class CompletionOrderConstraintTests(TestCase):
    """completion_order must be unique per (instance_date) when non-null."""

    def setUp(self):
        self.domain = Domain.objects.create(name="D", sort_order=0)
        self.project = Project.objects.create(name="P", domain=self.domain)
        self.date = datetime.date(2026, 6, 1)

    def test_duplicate_completion_order_same_date_raises(self):
        t1 = Task.objects.create(name="A", project=self.project)
        t2 = Task.objects.create(name="B", domain=Domain.objects.create(name="D2", sort_order=0))
        TaskInstance.objects.create(
            task=t1, instance_date=self.date,
            status="complete", completion_order=1,
        )
        with self.assertRaises(IntegrityError):
            TaskInstance.objects.create(
                task=t2, instance_date=self.date,
                status="complete", completion_order=1,
            )

    def test_null_completion_order_allowed_multiple(self):
        """Multiple incomplete instances (null completion_order) on the same date is fine."""
        for i in range(3):
            t = Task.objects.create(
                name=f"T{i}",
                domain=Domain.objects.create(name=f"D{i}", sort_order=i),
            )
            TaskInstance.objects.create(task=t, instance_date=self.date)
        self.assertEqual(
            TaskInstance.objects.filter(
                instance_date=self.date, completion_order__isnull=True,
            ).count(),
            3,
        )

    def test_same_order_different_dates_ok(self):
        t1 = Task.objects.create(name="A", project=self.project)
        t2 = Task.objects.create(name="B", domain=Domain.objects.create(name="D2", sort_order=0))
        TaskInstance.objects.create(
            task=t1, instance_date=self.date,
            status="complete", completion_order=1,
        )
        next_day = self.date + datetime.timedelta(days=1)
        TaskInstance.objects.create(
            task=t2, instance_date=next_day,
            status="complete", completion_order=1,
        )
        self.assertEqual(TaskInstance.objects.filter(completion_order=1).count(), 2)


class CompletionOrderTests(TestCase):
    """completion_order must auto-increment per day via the complete endpoint."""

    def setUp(self):
        self.domain = Domain.objects.create(name="D", sort_order=0)
        self.project = Project.objects.create(name="P", domain=self.domain)
        self.date = timezone.localdate()
        self.instances = []
        for i in range(3):
            task = Task.objects.create(
                name=f"Task {i}", project=self.project,
            )
            inst = TaskInstance.objects.create(
                task=task, instance_date=self.date,
            )
            self.instances.append(inst)

    def _complete(self, instance):
        resp = self.client.post(
            "/tasks/today/complete/",
            {"task_instance_id": instance.pk},
        )
        instance.refresh_from_db()
        return resp

    def test_first_completion_order_is_one(self):
        self._complete(self.instances[0])
        self.assertEqual(self.instances[0].completion_order, 1)
        self.assertEqual(self.instances[0].status, "complete")

    def test_orders_increment(self):
        self._complete(self.instances[0])
        self._complete(self.instances[1])
        self._complete(self.instances[2])
        self.assertEqual(self.instances[0].completion_order, 1)
        self.assertEqual(self.instances[1].completion_order, 2)
        self.assertEqual(self.instances[2].completion_order, 3)

    def test_uncomplete_clears_order(self):
        self._complete(self.instances[0])
        self.client.post(
            "/tasks/today/uncomplete/",
            {"task_instance_id": self.instances[0].pk},
        )
        self.instances[0].refresh_from_db()
        self.assertIsNone(self.instances[0].completion_order)
        self.assertEqual(self.instances[0].status, "incomplete")

    def test_recomplete_gets_next_order(self):
        self._complete(self.instances[0])
        self._complete(self.instances[1])
        # uncomplete #0 then re-complete — should get order 3
        self.client.post(
            "/tasks/today/uncomplete/",
            {"task_instance_id": self.instances[0].pk},
        )
        self._complete(self.instances[0])
        self.assertEqual(self.instances[0].completion_order, 3)

    def test_execution_log_preserved(self):
        self._complete(self.instances[0])
        self.client.post(
            "/tasks/today/uncomplete/",
            {"task_instance_id": self.instances[0].pk},
        )
        self._complete(self.instances[0])
        executions = list(
            TaskExecution.objects
            .filter(task_instance=self.instances[0])
            .order_by("event_at")
            .values_list("event_type", flat=True)
        )
        self.assertEqual(executions, ["completed", "uncompleted", "completed"])

    def test_different_days_independent_ordering(self):
        """completion_order resets per day."""
        yesterday = self.date - datetime.timedelta(days=1)
        task = Task.objects.create(name="Other", project=self.project)
        old_inst = TaskInstance.objects.create(task=task, instance_date=yesterday)
        old_inst.status = "complete"
        old_inst.completion_order = 99
        old_inst.save()

        self._complete(self.instances[0])
        # Today's first completion should be 1, not 100
        self.assertEqual(self.instances[0].completion_order, 1)


class ToggleCompleteTests(TestCase):
    """toggle_complete endpoint must assign/clear ordering correctly."""

    def setUp(self):
        self.domain = Domain.objects.create(name="D", sort_order=0)
        self.project = Project.objects.create(name="P", domain=self.domain)
        self.date = timezone.localdate()
        self.instances = []
        for i in range(4):
            task = Task.objects.create(
                name=f"T{i}", project=self.project,
            )
            inst = TaskInstance.objects.create(
                task=task, instance_date=self.date, assigned_order=i,
            )
            self.instances.append(inst)

    def _toggle(self, instance):
        self.client.post(
            f"/tasks/instances/{instance.pk}/toggle-complete/",
        )
        instance.refresh_from_db()

    def test_toggle_complete_assigns_order_and_timestamp(self):
        self._toggle(self.instances[0])
        self.assertEqual(self.instances[0].status, "complete")
        self.assertEqual(self.instances[0].completion_order, 1)
        self.assertIsNotNone(self.instances[0].completed_at)

    def test_toggle_uncomplete_clears_order_and_timestamp(self):
        self._toggle(self.instances[0])  # complete
        self._toggle(self.instances[0])  # uncomplete
        self.assertEqual(self.instances[0].status, "incomplete")
        self.assertIsNone(self.instances[0].completion_order)
        self.assertIsNone(self.instances[0].completed_at)

    def test_toggle_sequential_orders(self):
        self._toggle(self.instances[0])
        self._toggle(self.instances[1])
        self._toggle(self.instances[2])
        self.assertEqual(self.instances[0].completion_order, 1)
        self.assertEqual(self.instances[1].completion_order, 2)
        self.assertEqual(self.instances[2].completion_order, 3)

    def test_toggle_recomplete_skips_gap(self):
        """Uncompleting and re-completing gets max+1, not the old value."""
        self._toggle(self.instances[0])  # order=1
        self._toggle(self.instances[1])  # order=2
        self._toggle(self.instances[0])  # uncomplete (None)
        self._toggle(self.instances[0])  # re-complete → order=3
        self.assertEqual(self.instances[0].completion_order, 3)
        self.assertEqual(self.instances[1].completion_order, 2)

    def test_interleaved_toggles_maintain_uniqueness(self):
        """Complex toggle sequence never produces duplicate orders."""
        self._toggle(self.instances[0])  # complete → 1
        self._toggle(self.instances[1])  # complete → 2
        self._toggle(self.instances[0])  # uncomplete → None
        self._toggle(self.instances[2])  # complete → 3
        self._toggle(self.instances[1])  # uncomplete → None
        self._toggle(self.instances[0])  # complete → 4
        self._toggle(self.instances[3])  # complete → 5
        self._toggle(self.instances[1])  # complete → 6

        orders = list(
            TaskInstance.objects
            .filter(instance_date=self.date, completion_order__isnull=False)
            .values_list("completion_order", flat=True)
        )
        self.assertEqual(len(orders), len(set(orders)), "Duplicate completion_order found")
        self.assertEqual(sorted(orders), [3, 4, 5, 6])

    def test_toggle_creates_execution_records(self):
        self._toggle(self.instances[0])  # completed
        self._toggle(self.instances[0])  # uncompleted
        self._toggle(self.instances[0])  # completed
        events = list(
            TaskExecution.objects
            .filter(task_instance=self.instances[0])
            .order_by("event_at")
            .values_list("event_type", flat=True)
        )
        self.assertEqual(events, ["completed", "uncompleted", "completed"])


class TodayViewOrderingTests(TestCase):
    """The today view must return incomplete first, then complete, properly sorted."""

    def setUp(self):
        self.factory = RequestFactory()
        self.domain = Domain.objects.create(name="D", sort_order=0, color_hex="#111111")
        self.project = Project.objects.create(name="P", domain=self.domain)
        self.date = timezone.localdate()

    def _make_instance(self, name, status="incomplete", assigned_order=0,
                       priority=0, completion_order=None):
        task = Task.objects.create(
            name=name, project=self.project, priority=priority,
        )
        return TaskInstance.objects.create(
            task=task,
            instance_date=self.date,
            status=status,
            assigned_order=assigned_order,
            completion_order=completion_order,
        )

    def _get_ordered_names(self):
        request = self.factory.get("/tasks/today/")
        request.user = type("U", (), {"is_authenticated": False})()
        response = today(request)
        content = response.content.decode()
        # Extract task names from the rendered HTML in order
        import re
        # Task names appear inside the bold div after the dot span
        matches = re.findall(
            r'<div style="font-weight: 600;[^"]*">\s*\n?\s*(.+?)\s*\n?\s*</div>',
            content,
        )
        return [m.strip() for m in matches]

    def test_incomplete_before_complete(self):
        self._make_instance("Done", status="complete", completion_order=1)
        self._make_instance("Todo", status="incomplete")
        names = self._get_ordered_names()
        self.assertEqual(names, ["Todo", "Done"])

    def test_incomplete_sorted_by_assigned_order_then_priority(self):
        self._make_instance("C", assigned_order=2, priority=0)
        self._make_instance("A", assigned_order=1, priority=0)
        self._make_instance("B", assigned_order=1, priority=5)
        names = self._get_ordered_names()
        self.assertEqual(names, ["A", "B", "C"])

    def test_complete_sorted_by_completion_order(self):
        self._make_instance("Second", status="complete", completion_order=2)
        self._make_instance("First", status="complete", completion_order=1)
        names = self._get_ordered_names()
        self.assertEqual(names, ["First", "Second"])

    def test_skipped_after_complete(self):
        self._make_instance("Skipped", status="skipped")
        self._make_instance("Done", status="complete", completion_order=1)
        self._make_instance("Todo", status="incomplete")
        names = self._get_ordered_names()
        self.assertEqual(names, ["Todo", "Done", "Skipped"])
