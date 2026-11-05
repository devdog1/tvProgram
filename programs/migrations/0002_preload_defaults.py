from django.db import migrations

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


def load_defaults(apps, schema_editor):
    Category = apps.get_model("programs", "Category")
    Community = apps.get_model("programs", "Community")
    SourceCode = apps.get_model("programs", "SourceCode")
    ShareOption = apps.get_model("programs", "ShareOption")

    for code, label in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(
            name=code,
            defaults={"display_name": label, "is_enabled": True},
        )

    for comm in DEFAULT_COMMUNITIES:
        Community.objects.get_or_create(
            name=comm,
            defaults={"is_enabled": True},
        )

    for sc in DEFAULT_SOURCE_CODES:
        SourceCode.objects.get_or_create(
            name=sc,
            defaults={"is_enabled": True},
        )

    for sh in DEFAULT_SHARE_OPTIONS:
        ShareOption.objects.get_or_create(
            name=sh,
            defaults={"is_enabled": True},
        )


def unload_defaults(apps, schema_editor):
    Category = apps.get_model("programs", "Category")
    Community = apps.get_model("programs", "Community")
    SourceCode = apps.get_model("programs", "SourceCode")
    ShareOption = apps.get_model("programs", "ShareOption")

    Category.objects.all().delete()
    Community.objects.all().delete()
    SourceCode.objects.all().delete()
    ShareOption.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("programs", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(load_defaults, reverse_code=unload_defaults),
    ]
