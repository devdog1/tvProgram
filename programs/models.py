from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=100, blank=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self):
        return self.display_name or self.name


class Community(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Communities"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SourceCode(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Source Code"
        verbose_name_plural = "Source Codes"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ShareOption(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Share With Option"
        verbose_name_plural = "Share With Options"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Series(models.Model):
    SERIES_TYPE_CHOICES = [
        ("tv_series", "TV Series"),
        ("mini_series", "Mini-Series"),
        ("multi_part", "Multi-Part Program"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending_review", "Pending Sign-off"),
        ("signed_off", "Signed Off / Approved"),
        ("rejected", "Rejected"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    series_type = models.CharField(max_length=50, choices=SERIES_TYPE_CHOICES, default="tv_series")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="draft")

    # Creator & sign-off
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_series",
    )
    signed_off_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signed_off_series",
    )
    signed_off_at = models.DateTimeField(null=True, blank=True)
    sign_off_notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Series"
        verbose_name_plural = "Series"
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} ({self.get_series_type_display()})"


class Program(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending_review", "Pending Sign-off"),
        ("signed_off", "Signed Off / Approved"),
        ("rejected", "Rejected"),
    ]

    title = models.CharField(max_length=255, db_index=True)
    date_recorded = models.DateField(db_column="dateRecorded", db_index=True)
    expiry_date = models.DateField(db_column="expiryDate", null=True, blank=True, db_index=True)
    producer = models.CharField(max_length=255, db_index=True)
    length = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                regex=r"^\d{2}:\d{2}:\d{2}$",
                message="Length must be in HH:MM:SS format.",
            )
        ],
    )
    category = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    community = models.TextField(blank=True, null=True, help_text="Comma-separated list of communities")
    share = models.TextField(blank=True, null=True, help_text="Comma-separated list of share regions")
    source_code = models.CharField(max_length=255, db_column="sourceCode", blank=True, null=True, db_index=True)
    filename = models.CharField(
        max_length=255,
        db_index=True,
        validators=[
            RegexValidator(
                regex=r'^[^\\/:*?"<>|]+\.[a-zA-Z0-9]{1,5}$',
                message="Filename must be valid with an extension (e.g., myfile.mp4).",
            )
        ],
    )
    comments = models.CharField(max_length=255, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    # User authorship
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_programs",
    )

    # Series link for episodic/multi-part programs
    series = models.ForeignKey(
        Series,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="episodes",
    )
    season_number = models.PositiveIntegerField(null=True, blank=True, help_text="Season number (for TV series)")
    episode_number = models.PositiveIntegerField(null=True, blank=True, help_text="Episode or part number")
    part_number = models.PositiveIntegerField(null=True, blank=True, help_text="Part number (for multi-part programs)")

    # Review / sign-off workflow
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="draft")
    signed_off_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signed_off_programs",
    )
    signed_off_at = models.DateTimeField(null=True, blank=True)
    sign_off_notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "programs"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.id} - {self.title}"

    @property
    def community_list(self):
        if not self.community:
            return []
        return [c.strip() for c in self.community.split(",") if c.strip()]

    @property
    def share_list(self):
        if not self.share:
            return []
        return [s.strip() for s in self.share.split(",") if s.strip()]


class ProgramAttachment(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="program_attachments/%Y/%m/")
    filename = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_attachments",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.filename and self.file:
            self.filename = self.file.name.split("/")[-1]
        if self.file and hasattr(self.file, "size"):
            self.file_size = self.file.size
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.filename} ({self.program.title})"


class CustomField(models.Model):
    FIELD_TYPE_CHOICES = [
        ("text", "Text (Single line)"),
        ("textarea", "Long Text (Multi-line)"),
        ("integer", "Integer"),
        ("boolean", "Boolean (Yes/No)"),
        ("date", "Date"),
        ("url", "URL"),
    ]

    name = models.SlugField(max_length=50, unique=True, help_text="Internal identifier (slug), e.g. license_code")
    label = models.CharField(max_length=100, help_text="User visible label, e.g. License Code")
    field_type = models.CharField(max_length=20, choices=FIELD_TYPE_CHOICES, default="text")
    required = models.BooleanField(default=False)
    default_value = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} ({self.get_field_type_display()})"


class CustomFieldValue(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="custom_field_values")
    custom_field = models.ForeignKey(CustomField, on_delete=models.CASCADE, related_name="values")
    value = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("program", "custom_field")

    def __str__(self):
        return f"{self.program.title} - {self.custom_field.label}: {self.value}"


class ChangeLog(models.Model):
    ACTION_CHOICES = [
        ("Created", "Created"),
        ("Updated", "Updated"),
        ("Deleted", "Deleted"),
        ("Signed Off", "Signed Off"),
        ("Rejected", "Rejected"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="change_logs",
    )
    user_display = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100)
    object_repr = models.CharField(max_length=255)
    details = models.TextField(blank=True, help_text="JSON or text description of changes")

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.timestamp} - {self.user_display} - {self.action} {self.object_type} {self.object_repr}"


class EventHook(models.Model):
    EVENT_CHOICES = [
        ("program_created", "Program Created / Added"),
        ("program_updated", "Program Updated"),
        ("program_signed_off", "Program Signed Off / Approved"),
        ("program_rejected", "Program Rejected"),
        ("series_created", "Series Created"),
        ("series_signed_off", "Series Signed Off / Approved"),
    ]

    ACTION_CHOICES = [
        ("email", "Send Email Notification"),
        ("webhook", "Call Webhook (HTTP POST)"),
    ]

    name = models.CharField(max_length=150, help_text="A friendly name for this event hook")
    event_type = models.CharField(max_length=50, choices=EVENT_CHOICES, db_index=True)
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES, default="email")
    is_active = models.BooleanField(default=True)

    # Email configuration
    recipient_emails = models.TextField(
        blank=True,
        help_text="Comma-separated or newline-separated recipient email addresses",
    )
    email_subject = models.CharField(
        max_length=255,
        blank=True,
        default="[WCGtv Notification] {event}: {title}",
        help_text="Subject line template. Variables: {event}, {title}, {id}, {producer}, {user}",
    )
    email_body = models.TextField(
        blank=True,
        default="A new event occurred in WCGtv.\n\nEvent: {event}\nTitle: {title}\nProducer: {producer}\nTriggered by: {user}\nDetails: {details}",
        help_text="Email body template. Variables: {event}, {title}, {id}, {producer}, {user}, {details}",
    )

    # Webhook configuration
    webhook_url = models.URLField(blank=True, help_text="Target URL for POST requests")
    webhook_secret = models.CharField(max_length=255, blank=True, help_text="Optional secret key sent in headers")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_hooks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_triggered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_event_type_display()} -> {self.get_action_type_display()})"

    @property
    def recipient_list(self):
        if not self.recipient_emails:
            return []
        import re
        raw = re.split(r"[,\n\r]+", self.recipient_emails)
        return [r.strip() for r in raw if r.strip()]
