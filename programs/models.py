from django.db import models
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


class Program(models.Model):
    title = models.CharField(max_length=255)
    date_recorded = models.DateField(db_column="dateRecorded")
    expiry_date = models.DateField(db_column="expiryDate", null=True, blank=True)
    producer = models.CharField(max_length=255)
    length = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                regex=r"^\d{2}:\d{2}:\d{2}$",
                message="Length must be in HH:MM:SS format.",
            )
        ],
    )
    category = models.CharField(max_length=100, blank=True, null=True)
    community = models.TextField(blank=True, null=True, help_text="Comma-separated list of communities")
    share = models.TextField(blank=True, null=True, help_text="Comma-separated list of share regions")
    source_code = models.CharField(max_length=255, db_column="sourceCode", blank=True, null=True)
    filename = models.CharField(
        max_length=255,
        validators=[
            RegexValidator(
                regex=r'^[^\\/:*?"<>|]+\.[a-zA-Z0-9]{1,5}$',
                message="Filename must be valid with an extension (e.g., myfile.mp4).",
            )
        ],
    )
    comments = models.CharField(max_length=255, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)

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
