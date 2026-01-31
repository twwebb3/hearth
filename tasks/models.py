from django.conf import settings
from django.db import models


class Domain(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    color_hex = models.CharField(max_length=7, default="#6B7280")
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        indexes = [
            models.Index(fields=["sort_order", "name"]),
        ]

    def __str__(self):
        return self.name


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETE = "complete", "Complete"
        ARCHIVED = "archived", "Archived"

    domain = models.ForeignKey(
        Domain, on_delete=models.CASCADE, related_name="projects"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    color_hex = models.CharField(max_length=7, blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["domain", "status"]),
        ]

    def __str__(self):
        return self.name


class Task(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="tasks",
        null=True, blank=True,
    )
    domain = models.ForeignKey(
        Domain, on_delete=models.CASCADE, related_name="tasks",
        null=True, blank=True,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    priority = models.IntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["due_date"],
                condition=models.Q(due_date__isnull=False),
                name="tasks_task_due_date_notnull",
            ),
            models.Index(fields=["assigned_to", "is_active"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(project__isnull=False, domain__isnull=True)
                    | models.Q(project__isnull=True, domain__isnull=False)
                ),
                name="task_project_xor_domain",
            ),
        ]

    @property
    def effective_domain(self):
        """Return the domain — either direct or via project."""
        if self.domain_id:
            return self.domain
        return self.project.domain if self.project_id else None

    def __str__(self):
        return self.name


class TaskScheduleRule(models.Model):
    task = models.OneToOneField(
        Task, on_delete=models.CASCADE, related_name="schedule_rule"
    )
    rrule = models.TextField(help_text="iCal RRULE string")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    timezone = models.CharField(max_length=63, default="America/New_York")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Schedule for {self.task}"


class TaskInstance(models.Model):
    class Status(models.TextChoices):
        INCOMPLETE = "incomplete", "Incomplete"
        COMPLETE = "complete", "Complete"
        SKIPPED = "skipped", "Skipped"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        GENERATED = "generated", "Generated"
        ROLLED_OVER = "rolled_over", "Rolled Over"

    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, related_name="instances"
    )
    instance_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.INCOMPLETE
    )
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.MANUAL
    )
    assigned_order = models.IntegerField(default=0)
    completion_order = models.IntegerField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    skipped_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["task", "instance_date"],
                name="unique_task_instance_date",
            ),
            models.UniqueConstraint(
                fields=["instance_date", "completion_order"],
                condition=models.Q(completion_order__isnull=False),
                name="unique_completion_order_per_date",
            ),
        ]
        indexes = [
            models.Index(fields=["instance_date", "status"]),
            models.Index(fields=["task", "instance_date"]),
            models.Index(fields=["instance_date", "completion_order"]),
            models.Index(fields=["instance_date", "source"]),
        ]

    def __str__(self):
        return f"{self.task} – {self.instance_date}"


class TaskExecution(models.Model):
    class EventType(models.TextChoices):
        COMPLETED = "completed", "Completed"
        UNCOMPLETED = "uncompleted", "Uncompleted"
        SKIPPED = "skipped", "Skipped"
        UNSKIPPED = "unskipped", "Unskipped"

    task_instance = models.ForeignKey(
        TaskInstance, on_delete=models.CASCADE, related_name="executions"
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_executions",
    )
    event_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["task_instance", "event_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} @ {self.event_at}"
