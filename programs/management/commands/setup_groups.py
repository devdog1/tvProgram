from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from programs.models import Program, Category, Community, SourceCode, ShareOption


class Command(BaseCommand):
    help = "Setup default user groups and permissions"

    def handle(self, *args, **options):
        # 1. Program Creator group: can create programs and view programs
        creator_group, _ = Group.objects.get_or_create(name="Program Creators")
        ct_program = ContentType.objects.get_for_model(Program)
        p_add_program = Permission.objects.get(content_type=ct_program, codename="add_program")
        p_view_program = Permission.objects.get(content_type=ct_program, codename="view_program")
        creator_group.permissions.add(p_add_program, p_view_program)

        # 2. Program Editors group: can create, change, delete programs AND manage options
        editor_group, _ = Group.objects.get_or_create(name="Program Editors")
        option_models = [Category, Community, SourceCode, ShareOption, Program]
        for model in option_models:
            ct = ContentType.objects.get_for_model(model)
            for action in ["add", "change", "delete", "view"]:
                perm = Permission.objects.get(content_type=ct, codename=f"{action}_{model._meta.model_name}")
                editor_group.permissions.add(perm)

        self.stdout.write(self.style.SUCCESS("Successfully set up default user groups and permissions."))
