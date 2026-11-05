from django.core.management.base import BaseCommand
from programs.models import Category, Community, SourceCode, ShareOption


DEFAULT_CATEGORIES = [
    ("arts/music", "Arts/Music"),
    ("sports", "Sports"),
    ("religion", "Religion"),
    ("games/bingo", "Games/Bingo"),
    ("current affairs", "Current Affairs"),
    ("educational", "Educational"),
    ("filler", "Filler"),
    ("special events", "Special Events"),
    ("documentary", "Documentary"),
    ("promotion", "Promotion"),
    ("interview", "Interview"),
]

DEFAULT_COMMUNITIES = [
    "Birtle",
    "Boissevain",
    "Brandon",
    "Carberry",
    "Dauphin",
    "Deloraine",
    "Gilbert Plains",
    "Gladstone",
    "Killarney",
    "Melita",
    "Minnedosa",
    "Rivers",
    "Roblin",
    "Russell",
    "Souris",
    "Ste. Rose",
    "Swan River",
    "Virden",
]

DEFAULT_SOURCE_CODES = [
    "a - Single Camera/No Editing",
    "b - Single Camera Edited",
    "c - Multi Cameras Mixed on Site",
    "d - Multi Cameras Mixed on Site with Audio (minimum 4 person crew)",
    "e - Studio Production - Minimum 2 cameras",
]

DEFAULT_SHARE_OPTIONS = [
    "All",
    "Brandon",
    "North",
    "South",
]


class Command(BaseCommand):
    help = "Preload system default options from the PHP index file"

    def handle(self, *args, **options):
        # Preload Categories
        for code, label in DEFAULT_CATEGORIES:
            cat, created = Category.objects.get_or_create(
                name=code,
                defaults={"display_name": label, "is_enabled": True},
            )
            if not created and not cat.display_name:
                cat.display_name = label
                cat.save()

        # Preload Communities
        for comm in DEFAULT_COMMUNITIES:
            Community.objects.get_or_create(
                name=comm,
                defaults={"is_enabled": True},
            )

        # Preload Source Codes
        for sc in DEFAULT_SOURCE_CODES:
            SourceCode.objects.get_or_create(
                name=sc,
                defaults={"is_enabled": True},
            )

        # Preload Share With options
        for sh in DEFAULT_SHARE_OPTIONS:
            ShareOption.objects.get_or_create(
                name=sh,
                defaults={"is_enabled": True},
            )

        self.stdout.write(self.style.SUCCESS("Successfully preloaded system default options."))
