from django.contrib import admin
from .models import Program, Category, Community, SourceCode, ShareOption


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
