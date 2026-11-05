from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .models import Program, Category, Community, SourceCode, ShareOption
from .forms import ProgramForm, CategoryForm, CommunityForm, SourceCodeForm, ShareOptionForm


def can_edit_options(user):
    return user.is_authenticated and (
        user.is_superuser or
        user.has_perm("programs.change_category") or
        user.has_perm("programs.change_program") or
        user.groups.filter(name="Program Editors").exists()
    )


def can_create_program(user):
    return user.is_authenticated and (
        user.is_superuser or
        user.has_perm("programs.add_program") or
        user.groups.filter(name__in=["Program Creators", "Program Editors"]).exists()
    )


def can_edit_program(user):
    return user.is_authenticated and (
        user.is_superuser or
        user.has_perm("programs.change_program") or
        user.groups.filter(name="Program Editors").exists()
    )


def can_delete_program(user):
    return user.is_authenticated and (
        user.is_superuser or
        user.has_perm("programs.delete_program") or
        user.groups.filter(name="Program Editors").exists()
    )


@login_required
def program_list(request):
    programs = Program.objects.all().order_by("-id")
    can_edit = can_edit_program(request.user)
    can_del = can_delete_program(request.user)
    can_create = can_create_program(request.user)
    can_opts = can_edit_options(request.user)
    return render(
        request,
        "programs/program_list.html",
        {
            "programs": programs,
            "can_edit": can_edit,
            "can_delete": can_del,
            "can_create": can_create,
            "can_edit_options": can_opts,
        },
    )


@login_required
def program_create(request):
    if not can_create_program(request.user):
        return HttpResponseForbidden("You do not have permission to create programs.")

    if request.method == "POST":
        form = ProgramForm(request.POST)
        if form.is_valid():
            program = form.save()
            messages.success(request, f"Program '{program.title}' created successfully.")

            # If user checked 'Download text file like PHP index.php' or requested download
            if request.POST.get("download_txt") == "1":
                filename_base = program.filename
                if "." in filename_base:
                    filename_txt = filename_base[: filename_base.rfind(".")] + ".txt"
                else:
                    filename_txt = f"{filename_base}.txt"

                lines = []
                lines.append(f"title: {program.title}")
                lines.append(f"dateRecorded: {program.date_recorded}")
                if program.expiry_date:
                    lines.append(f"expiryDate: {program.expiry_date}")
                lines.append(f"producer: {program.producer}")
                lines.append(f"length: {program.length}")
                if program.category:
                    lines.append(f"category: {program.category}")
                if program.community:
                    lines.append(f"community: {program.community}")
                if program.source_code:
                    lines.append(f"sourceCode: {program.source_code}")
                if program.share:
                    lines.append(f"share: {program.share}")
                lines.append(f"filename: {program.filename}")
                if program.comments:
                    lines.append(f"comments: {program.comments}")
                content = "\n".join(lines) + "\n"

                response = HttpResponse(content, content_type="text/plain")
                response["Content-Disposition"] = f'attachment; filename="{filename_txt}"'
                return response

            return redirect("program_list")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ProgramForm()

    return render(
        request,
        "programs/program_form.html",
        {
            "form": form,
            "action": "Create",
            "can_edit_options": can_edit_options(request.user),
        },
    )


@login_required
def program_edit(request, pk):
    if not can_edit_program(request.user):
        return HttpResponseForbidden("You do not have permission to edit programs.")

    program = get_object_or_404(Program, pk=pk)
    if request.method == "POST":
        form = ProgramForm(request.POST, instance=program)
        if form.is_valid():
            form.save()
            messages.success(request, f"Program '{program.title}' updated successfully.")
            return redirect("program_list")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ProgramForm(instance=program)

    return render(
        request,
        "programs/program_form.html",
        {
            "form": form,
            "program": program,
            "action": "Edit",
            "can_edit_options": can_edit_options(request.user),
        },
    )


@login_required
def program_delete(request, pk):
    if not can_delete_program(request.user):
        return HttpResponseForbidden("You do not have permission to delete programs.")

    program = get_object_or_404(Program, pk=pk)
    if request.method == "POST":
        title = program.title
        program.delete()
        messages.success(request, f"Program '{title}' deleted successfully.")
        return redirect("program_list")

    return render(
        request,
        "programs/program_confirm_delete.html",
        {
            "program": program,
            "can_edit_options": can_edit_options(request.user),
        },
    )


# Option management views (Categories, Communities, Source Codes, Share With)
OPTION_CONFIGS = {
    "category": {
        "title": "Categories",
        "singular": "Category",
        "model": Category,
        "form": CategoryForm,
    },
    "community": {
        "title": "Communities",
        "singular": "Community",
        "model": Community,
        "form": CommunityForm,
    },
    "source_code": {
        "title": "Source Codes",
        "singular": "Source Code",
        "model": SourceCode,
        "form": SourceCodeForm,
    },
    "share_option": {
        "title": "Share With Options",
        "singular": "Share With Option",
        "model": ShareOption,
        "form": ShareOptionForm,
    },
}


@login_required
def options_dashboard(request):
    if not can_edit_options(request.user):
        return HttpResponseForbidden("You do not have permission to manage options.")

    return render(
        request,
        "programs/options_dashboard.html",
        {
            "categories": Category.objects.all().order_by("name"),
            "communities": Community.objects.all().order_by("name"),
            "source_codes": SourceCode.objects.all().order_by("name"),
            "share_options": ShareOption.objects.all().order_by("name"),
            "can_edit_options": True,
        },
    )


@login_required
def option_create(request, opt_type):
    if not can_edit_options(request.user):
        return HttpResponseForbidden("You do not have permission to manage options.")

    config = OPTION_CONFIGS.get(opt_type)
    if not config:
        return redirect("options_dashboard")

    ModelFormClass = config["form"]
    if request.method == "POST":
        form = ModelFormClass(request.POST)
        if form.is_valid():
            item = form.save()
            messages.success(request, f"{config['singular']} '{item}' created successfully.")
            return redirect("options_dashboard")
    else:
        form = ModelFormClass()

    return render(
        request,
        "programs/option_form.html",
        {
            "form": form,
            "opt_type": opt_type,
            "config": config,
            "action": "Create",
            "can_edit_options": True,
        },
    )


@login_required
def option_edit(request, opt_type, pk):
    if not can_edit_options(request.user):
        return HttpResponseForbidden("You do not have permission to manage options.")

    config = OPTION_CONFIGS.get(opt_type)
    if not config:
        return redirect("options_dashboard")

    ModelClass = config["model"]
    ModelFormClass = config["form"]
    item = get_object_or_404(ModelClass, pk=pk)

    if request.method == "POST":
        form = ModelFormClass(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f"{config['singular']} '{item}' updated successfully.")
            return redirect("options_dashboard")
    else:
        form = ModelFormClass(instance=item)

    return render(
        request,
        "programs/option_form.html",
        {
            "form": form,
            "opt_type": opt_type,
            "config": config,
            "action": "Edit",
            "item": item,
            "can_edit_options": True,
        },
    )


@login_required
def option_toggle(request, opt_type, pk):
    if not can_edit_options(request.user):
        return HttpResponseForbidden("You do not have permission to manage options.")

    config = OPTION_CONFIGS.get(opt_type)
    if not config:
        return redirect("options_dashboard")

    ModelClass = config["model"]
    item = get_object_or_404(ModelClass, pk=pk)
    if request.method == "POST":
        item.is_enabled = not item.is_enabled
        item.save()
        status_str = "enabled" if item.is_enabled else "disabled"
        messages.success(request, f"{config['singular']} '{item}' {status_str}.")

    return redirect("options_dashboard")
