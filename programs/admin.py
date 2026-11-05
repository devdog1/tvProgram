from django.contrib import admin
from .models import Program, Category, Community, SourceCode, ShareOption, Series, CustomField, EventHook, SMTPSettings, APIKey


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "date_recorded", "expiry_date", "producer", "length", "category", "source_code", "filename", "created")
    search_fields = ("title", "producer", "filename", "comments")
    list_filter = ("category", "source_code", "date_recorded")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "display_name", "is_enabled", "created_at")
    list_filter = ("is_enabled",)
    search_fields = ("name", "display_name")


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ("name", "is_enabled", "created_at")
    list_filter = ("is_enabled",)
    search_fields = ("name",)


@admin.register(SMTPSettings)
class SMTPSettingsAdmin(admin.ModelAdmin):
    list_display = ("host", "port", "from_address", "envelope_from", "use_tls", "use_ssl", "is_active", "updated_at")
    list_filter = ("is_active", "use_tls", "use_ssl")
    search_fields = ("host", "from_address", "envelope_from")
    fieldsets = (
        ("Relay Server Connection", {
            "fields": ("host", "port", "username", "password", "use_tls", "use_ssl", "timeout", "is_active")
        }),
        ("Sender & Postfix Envelope Options", {
            "fields": ("from_address", "envelope_from"),
            "description": "Set the From header address and Postfix envelope from (Return-Path). If envelope from is empty, from address is used."
        }),
    )


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "prefix", "user", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "key", "prefix", "user__username")
    readonly_fields = ("prefix", "created_at", "last_used_at")


@admin.register(SourceCode)
class SourceCodeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_enabled", "created_at")
    list_filter = ("is_enabled",)
    search_fields = ("name",)


@admin.register(ShareOption)
class ShareOptionAdmin(admin.ModelAdmin):
    list_display = ("name", "is_enabled", "created_at")
    list_filter = ("is_enabled",)
    search_fields = ("name",)
