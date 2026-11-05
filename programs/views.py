from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.db.models import Q

from .models import (
    Program,
    Category,
    Community,
    SourceCode,
    ShareOption,
    Series,
    CustomField,
    CustomFieldValue,
    ProgramAttachment,
    ChangeLog,
    EventHook,
)
from .forms import (
    ProgramForm,
    SeriesForm,
    CustomFieldForm,
    CategoryForm,
    CommunityForm,
    SourceCodeForm,
    ShareOptionForm,
    EventHookForm,
)
from .services import (
    log_change,
    can_edit_program,
    can_delete_program,
    can_sign_off,
    trigger_event_hooks,
)


@login_required
def dashboard_view(request):
    programs_count = Program.objects.count()
    signed_off_count = Program.objects.filter(status="signed_off").count()
    pending_review_count = Program.objects.filter(status="pending_review").count()
    draft_count = Program.objects.filter(status="draft").count()

    series_count = Series.objects.count()
    tv_series_count = Series.objects.filter(series_type="tv_series").count()
    mini_series_count = Series.objects.filter(series_type="mini_series").count()
    multi_part_count = Series.objects.filter(series_type="multi_part").count()

    categories_count = Category.objects.count()
    communities_count = Community.objects.count()
    source_codes_count = SourceCode.objects.count()
    custom_fields_count = CustomField.objects.count()
    event_hooks_count = EventHook.objects.count()

    recent_logs = ChangeLog.objects.all()[:10]

    return render(
        request,
        "programs/dashboard.html",
        {
            "programs_count": programs_count,
            "signed_off_count": signed_off_count,
            "pending_review_count": pending_review_count,
            "draft_count": draft_count,
            "series_count": series_count,
            "tv_series_count": tv_series_count,
            "mini_series_count": mini_series_count,
            "multi_part_count": multi_part_count,
            "categories_count": categories_count,
            "communities_count": communities_count,
            "source_codes_count": source_codes_count,
            "custom_fields_count": custom_fields_count,
            "event_hooks_count": event_hooks_count,
            "recent_logs": recent_logs,
        },
    )


@login_required
def program_list(request):
    programs = Program.objects.select_related("series", "created_by").all()
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()

    if q:
        programs = programs.filter(
            Q(title__icontains=q)
            | Q(producer__icontains=q)
            | Q(filename__icontains=q)
            | Q(comments__icontains=q)
            | Q(series__title__icontains=q)
        )

    if status_filter:
        programs = programs.filter(status=status_filter)

    # Attach user permissions for template conditional rendering
    programs_with_perms = []
    for p in programs:
        p.user_can_edit = can_edit_program(request.user, p)
        p.user_can_delete = can_delete_program(request.user, p)
        programs_with_perms.append(p)

    return render(request, "programs/program_list.html", {"programs": programs_with_perms})


@login_required
def program_detail(request, pk):
    program = get_object_or_404(
        Program.objects.select_related("series", "created_by", "signed_off_by").prefetch_related("attachments"),
        pk=pk,
    )
    user_can_edit = can_edit_program(request.user, program)
    user_can_delete = can_delete_program(request.user, program)
    user_can_approve = can_sign_off(request.user)

    # Custom fields data
    active_custom_fields = CustomField.objects.filter(is_active=True)
    existing_values = {v.custom_field_id: v.value for v in program.custom_field_values.all()}
    custom_fields_data = [
        {"field": f, "value": existing_values.get(f.id, f.default_value or "")}
        for f in active_custom_fields
    ]

    return render(
        request,
        "programs/program_detail.html",
        {
            "program": program,
            "can_edit": user_can_edit,
            "can_delete": user_can_delete,
            "user_can_approve": user_can_approve,
            "can_signoff_action": user_can_approve or user_can_edit,
            "custom_fields_data": custom_fields_data,
        },
    )


@login_required
@permission_required("programs.add_program", raise_exception=True)
def program_create(request):
    active_custom_fields = CustomField.objects.filter(is_active=True)

    if request.method == "POST":
        form = ProgramForm(request.POST)
        if form.is_valid():
            program = form.save(commit=False)
            program.created_by = request.user
            program.save()

            # Save custom fields
            for cf in active_custom_fields:
                val = request.POST.get(f"custom_field_{cf.name}", "").strip()
                if val:
                    CustomFieldValue.objects.create(program=program, custom_field=cf, value=val)

            log_change(
                user=request.user,
                action="Created",
                instance=program,
                changes_dict={"title": program.title, "filename": program.filename, "created_by": request.user.username},
            )
            trigger_event_hooks(
                event_name="program_created",
                instance=program,
                user=request.user,
                details=f"Program '{program.title}' created by {request.user.username}",
            )

            messages.success(request, f"Program '{program.title}' was created successfully.")
            return redirect("program_detail", pk=program.pk)
    else:
        initial = {}
        series_id = request.GET.get("series")
        if series_id:
            try:
                series = Series.objects.get(pk=series_id)
                initial["series"] = series
            except Series.DoesNotExist:
                pass
        form = ProgramForm(initial=initial)

    custom_field_inputs = [
        {"field": cf, "value": cf.default_value or ""}
        for cf in active_custom_fields
    ]

    return render(
        request,
        "programs/program_form.html",
        {"form": form, "custom_field_inputs": custom_field_inputs},
    )


@login_required
def program_edit(request, pk):
    program = get_object_or_404(Program, pk=pk)

    if not can_edit_program(request.user, program):
        raise PermissionDenied("You do not have permission to edit this program.")

    active_custom_fields = CustomField.objects.filter(is_active=True)
    existing_values_map = {
        cfv.custom_field_id: cfv for cfv in program.custom_field_values.all()
    }

    if request.method == "POST":
        form = ProgramForm(request.POST, instance=program)
        if form.is_valid():
            updated_program = form.save()

            # Handle custom fields update
            changes_cf = {}
            for cf in active_custom_fields:
                new_val = request.POST.get(f"custom_field_{cf.name}", "").strip()
                cfv = existing_values_map.get(cf.id)
                if cfv:
                    if cfv.value != new_val:
                        changes_cf[cf.label] = {"from": cfv.value, "to": new_val}
                        cfv.value = new_val
                        cfv.save()
                elif new_val:
                    CustomFieldValue.objects.create(program=updated_program, custom_field=cf, value=new_val)
                    changes_cf[cf.label] = {"from": "", "to": new_val}

            log_change(
                user=request.user,
                action="Updated",
                instance=updated_program,
                changes_dict={"fields_changed": form.changed_data, "custom_fields": changes_cf},
            )
            trigger_event_hooks(
                event_name="program_updated",
                instance=updated_program,
                user=request.user,
                details=f"Fields changed: {', '.join(form.changed_data)}",
            )

            messages.success(request, f"Program '{updated_program.title}' was updated successfully.")
            return redirect("program_detail", pk=updated_program.pk)
    else:
        form = ProgramForm(instance=program)

    custom_field_inputs = [
        {
            "field": cf,
            "value": existing_values_map.get(cf.id).value if cf.id in existing_values_map else (cf.default_value or ""),
        }
        for cf in active_custom_fields
    ]

    return render(
        request,
        "programs/program_form.html",
        {"form": form, "custom_field_inputs": custom_field_inputs},
    )


@login_required
def program_delete(request, pk):
    program = get_object_or_404(Program, pk=pk)

    # Creators CANNOT delete their program unless they also possess delete_program permission
    if not can_delete_program(request.user, program):
        raise PermissionDenied("You do not have permission to delete programs.")

    if request.method == "POST":
        title = program.title
        prog_id = program.id
        log_change(
            user=request.user,
            action="Deleted",
            instance=program,
            changes_dict={"deleted_id": prog_id, "title": title},
        )
        program.delete()
        messages.success(request, f"Program '{title}' was deleted successfully.")
        return redirect("program_list")

    return render(request, "programs/program_confirm_delete.html", {"program": program})


@login_required
def program_signoff(request, pk):
    program = get_object_or_404(Program, pk=pk)
    if request.method != "POST":
        return redirect("program_detail", pk=pk)

    action = request.POST.get("action")
    notes = request.POST.get("notes", "").strip()

    if action == "submit_for_review":
        if not can_edit_program(request.user, program):
            raise PermissionDenied("You cannot submit this program for review.")
        program.status = "pending_review"
        program.sign_off_notes = notes
        program.save()
        log_change(request.user, "Updated", program, {"action": "Submitted for sign-off review", "notes": notes})
        messages.info(request, f"Program '{program.title}' was submitted for review.")

    elif action in ["approve", "reject", "reset_draft"]:
        if not can_sign_off(request.user):
            raise PermissionDenied("You do not have permission to validate or sign off programs.")

        if action == "approve":
            program.status = "signed_off"
            program.signed_off_by = request.user
            program.signed_off_at = timezone.now()
            program.sign_off_notes = notes
            program.save()
            log_change(request.user, "Signed Off", program, {"decision": "Approved", "notes": notes})
            trigger_event_hooks(
                event_name="program_signed_off",
                instance=program,
                user=request.user,
                details=f"Approved by {request.user.username}. Notes: {notes}",
            )
            messages.success(request, f"Program '{program.title}' has been signed off and approved.")
        elif action == "reject":
            program.status = "rejected"
            program.signed_off_by = request.user
            program.signed_off_at = timezone.now()
            program.sign_off_notes = notes
            program.save()
            log_change(request.user, "Rejected", program, {"decision": "Rejected", "notes": notes})
            trigger_event_hooks(
                event_name="program_rejected",
                instance=program,
                user=request.user,
                details=f"Rejected by {request.user.username}. Notes: {notes}",
            )
            messages.warning(request, f"Program '{program.title}' was rejected.")
        elif action == "reset_draft":
            program.status = "draft"
            program.sign_off_notes = notes
            program.save()
            log_change(request.user, "Updated", program, {"decision": "Reset to draft", "notes": notes})
            messages.info(request, f"Program '{program.title}' returned to draft.")

    return redirect("program_detail", pk=pk)


@login_required
def program_attach_file(request, pk):
    program = get_object_or_404(Program, pk=pk)
    if not can_edit_program(request.user, program):
        raise PermissionDenied("You do not have permission to attach files to this program.")

    if request.method == "POST" and request.FILES.get("file"):
        uploaded_file = request.FILES["file"]
        desc = request.POST.get("description", "").strip()

        attachment = ProgramAttachment.objects.create(
            program=program,
            file=uploaded_file,
            filename=uploaded_file.name,
            description=desc,
            uploaded_by=request.user,
        )

        log_change(
            request.user,
            "Updated",
            program,
            {"action": "Attached file", "filename": attachment.filename, "size": attachment.file_size},
        )
        messages.success(request, f"Attached '{attachment.filename}' to program.")

    return redirect("program_detail", pk=pk)


@login_required
def program_delete_attachment(request, attachment_id):
    attachment = get_object_or_404(ProgramAttachment, pk=attachment_id)
    program = attachment.program
    if not can_edit_program(request.user, program):
        raise PermissionDenied("You do not have permission to delete this attachment.")

    if request.method == "POST":
        fn = attachment.filename
        attachment.delete()
        log_change(request.user, "Updated", program, {"action": "Removed attachment", "filename": fn})
        messages.success(request, f"Removed attachment '{fn}'.")

    return redirect("program_detail", pk=program.pk)


# ==============================================================================
# TV Series & Multi-part Programs Views
# ==============================================================================

@login_required
def series_list(request):
    series = Series.objects.prefetch_related("episodes").select_related("created_by").all()
    return render(request, "programs/series_list.html", {"series_list": series})


@login_required
def series_detail(request, pk):
    series = get_object_or_404(Series.objects.prefetch_related("episodes").select_related("created_by", "signed_off_by"), pk=pk)
    user_can_approve = can_sign_off(request.user)
    return render(
        request,
        "programs/series_detail.html",
        {"series": series, "user_can_approve": user_can_approve},
    )


@login_required
def series_create(request):
    if request.method == "POST":
        form = SeriesForm(request.POST)
        if form.is_valid():
            series = form.save(commit=False)
            series.created_by = request.user
            series.save()
            log_change(request.user, "Created", series, {"title": series.title, "type": series.series_type})
            messages.success(request, f"Series '{series.title}' created.")
            return redirect("series_detail", pk=series.pk)
    else:
        form = SeriesForm()
    return render(request, "programs/series_form.html", {"form": form})


@login_required
def series_edit(request, pk):
    series = get_object_or_404(Series, pk=pk)
    if request.method == "POST":
        form = SeriesForm(request.POST, instance=series)
        if form.is_valid():
            s = form.save()
            log_change(request.user, "Updated", s, {"changed": form.changed_data})
            messages.success(request, f"Series '{s.title}' updated.")
            return redirect("series_detail", pk=s.pk)
    else:
        form = SeriesForm(instance=series)
    return render(request, "programs/series_form.html", {"form": form})


@login_required
def series_delete(request, pk):
    series = get_object_or_404(Series, pk=pk)
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("Only staff or admins can delete series.")

    if request.method == "POST":
        title = series.title
        log_change(request.user, "Deleted", series, {"title": title})
        series.delete()
        messages.success(request, f"Series '{title}' deleted.")
        return redirect("series_list")

    return render(request, "programs/program_confirm_delete.html", {"series": series})


@login_required
def series_signoff(request, pk):
    series = get_object_or_404(Series, pk=pk)
    if request.method != "POST":
        return redirect("series_detail", pk=pk)

    action = request.POST.get("action")
    notes = request.POST.get("notes", "").strip()

    if action == "submit_for_review":
        series.status = "pending_review"
        series.sign_off_notes = notes
        series.save()
        log_change(request.user, "Updated", series, {"action": "Submitted for sign-off review", "notes": notes})
        messages.info(request, f"Series '{series.title}' submitted for review.")
    elif action in ["approve", "reject", "reset_draft"]:
        if not can_sign_off(request.user):
            raise PermissionDenied("You do not have permission to validate or sign off series.")
        if action == "approve":
            series.status = "signed_off"
            series.signed_off_by = request.user
            series.signed_off_at = timezone.now()
            series.sign_off_notes = notes
            series.save()
            log_change(request.user, "Signed Off", series, {"decision": "Approved", "notes": notes})
            trigger_event_hooks(
                event_name="series_signed_off",
                instance=series,
                user=request.user,
                details=f"Approved by {request.user.username}. Notes: {notes}",
            )
            messages.success(request, f"Series '{series.title}' approved & signed off.")
        elif action == "reject":
            series.status = "rejected"
            series.signed_off_by = request.user
            series.signed_off_at = timezone.now()
            series.sign_off_notes = notes
            series.save()
            log_change(request.user, "Rejected", series, {"decision": "Rejected", "notes": notes})
            messages.warning(request, f"Series '{series.title}' rejected.")
        elif action == "reset_draft":
            series.status = "draft"
            series.sign_off_notes = notes
            series.save()
            log_change(request.user, "Updated", series, {"decision": "Reset to draft", "notes": notes})
            messages.info(request, f"Series '{series.title}' returned to draft.")

    return redirect("series_detail", pk=pk)


# ==============================================================================
# Custom Fields Management Views (Admins / Editors)
# ==============================================================================

@login_required
def custom_fields_list(request):
    if not (request.user.is_staff or request.user.is_superuser or request.user.has_perm("programs.change_category")):
        raise PermissionDenied("You do not have permission to manage custom fields.")
    fields = CustomField.objects.all()
    return render(request, "programs/custom_fields_list.html", {"custom_fields": fields})


@login_required
def custom_field_create(request):
    if not (request.user.is_staff or request.user.is_superuser or request.user.has_perm("programs.change_category")):
        raise PermissionDenied("You do not have permission to manage custom fields.")

    if request.method == "POST":
        form = CustomFieldForm(request.POST)
        if form.is_valid():
            cf = form.save()
            log_change(request.user, "Created", cf, {"label": cf.label, "name": cf.name, "type": cf.field_type})
            messages.success(request, f"Custom field '{cf.label}' created.")
            return redirect("custom_fields_list")
    else:
        form = CustomFieldForm()

    return render(request, "programs/custom_field_form.html", {"form": form})


@login_required
def custom_field_edit(request, pk):
    if not (request.user.is_staff or request.user.is_superuser or request.user.has_perm("programs.change_category")):
        raise PermissionDenied("You do not have permission to manage custom fields.")

    cf = get_object_or_404(CustomField, pk=pk)
    if request.method == "POST":
        form = CustomFieldForm(request.POST, instance=cf)
        if form.is_valid():
            cf = form.save()
            log_change(request.user, "Updated", cf, {"label": cf.label, "name": cf.name})
            messages.success(request, f"Custom field '{cf.label}' updated.")
            return redirect("custom_fields_list")
    else:
        form = CustomFieldForm(instance=cf)

    return render(request, "programs/custom_field_form.html", {"form": form})


@login_required
def custom_field_delete(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("Only administrators can delete custom fields.")

    cf = get_object_or_404(CustomField, pk=pk)
    if request.method == "POST":
        lbl = cf.label
        log_change(request.user, "Deleted", cf, {"label": lbl, "name": cf.name})
        cf.delete()
        messages.success(request, f"Custom field '{lbl}' deleted.")
        return redirect("custom_fields_list")

    return render(request, "programs/program_confirm_delete.html", {"custom_field": cf})


# ==============================================================================
# Sign-off Queue & Change Log Views
# ==============================================================================

@login_required
def signoff_queue(request):
    pending_programs = Program.objects.filter(status="pending_review").select_related("series", "created_by")
    pending_series = Series.objects.filter(status="pending_review").select_related("created_by")
    return render(
        request,
        "programs/signoff_queue.html",
        {"pending_programs": pending_programs, "pending_series": pending_series},
    )


@login_required
def changelog_list(request):
    logs = ChangeLog.objects.all()[:100]
    return render(request, "programs/changelog_list.html", {"logs": logs})


# ==============================================================================
# Event Hook Manager Views
# ==============================================================================

@login_required
def event_hooks_list(request):
    if not (request.user.is_staff or request.user.is_superuser or request.user.has_perm("programs.change_category")):
        raise PermissionDenied("You do not have permission to manage event hooks.")

    hooks = EventHook.objects.select_related("created_by").all()
    return render(request, "programs/event_hooks_list.html", {"hooks": hooks})


@login_required
def event_hook_create(request):
    if not (request.user.is_staff or request.user.is_superuser or request.user.has_perm("programs.change_category")):
        raise PermissionDenied("You do not have permission to manage event hooks.")

    if request.method == "POST":
        form = EventHookForm(request.POST)
        if form.is_valid():
            hook = form.save(commit=False)
            hook.created_by = request.user
            hook.save()
            log_change(request.user, "Created", hook, {"name": hook.name, "event": hook.event_type, "action": hook.action_type})
            messages.success(request, f"Event hook '{hook.name}' created.")
            return redirect("event_hooks_list")
    else:
        form = EventHookForm()

    return render(request, "programs/event_hook_form.html", {"form": form})


@login_required
def event_hook_edit(request, pk):
    if not (request.user.is_staff or request.user.is_superuser or request.user.has_perm("programs.change_category")):
        raise PermissionDenied("You do not have permission to manage event hooks.")

    hook = get_object_or_404(EventHook, pk=pk)
    if request.method == "POST":
        form = EventHookForm(request.POST, instance=hook)
        if form.is_valid():
            h = form.save()
            log_change(request.user, "Updated", h, {"name": h.name, "event": h.event_type})
            messages.success(request, f"Event hook '{h.name}' updated.")
            return redirect("event_hooks_list")
    else:
        form = EventHookForm(instance=hook)

    return render(request, "programs/event_hook_form.html", {"form": form})


@login_required
def event_hook_toggle(request, pk):
    if not (request.user.is_staff or request.user.is_superuser or request.user.has_perm("programs.change_category")):
        raise PermissionDenied("You do not have permission to manage event hooks.")

    hook = get_object_or_404(EventHook, pk=pk)
    hook.is_active = not hook.is_active
    hook.save()
    status_str = "activated" if hook.is_active else "deactivated"
    log_change(request.user, "Updated", hook, {"is_active": hook.is_active})
    messages.success(request, f"Event hook '{hook.name}' was {status_str}.")
    return redirect("event_hooks_list")


@login_required
def event_hook_delete(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("Only administrators can delete event hooks.")

    hook = get_object_or_404(EventHook, pk=pk)
    if request.method == "POST":
        name = hook.name
        log_change(request.user, "Deleted", hook, {"name": name})
        hook.delete()
        messages.success(request, f"Event hook '{name}' deleted.")
        return redirect("event_hooks_list")

    return render(request, "programs/program_confirm_delete.html", {"event_hook": hook})


# ==============================================================================
# Metadata Options Management Views
# ==============================================================================

MODEL_MAP = {
    "category": (Category, CategoryForm, "Category"),
    "community": (Community, CommunityForm, "Community"),
    "sourcecode": (SourceCode, SourceCodeForm, "Source Code"),
    "shareoption": (ShareOption, ShareOptionForm, "Share With Option"),
}


@login_required
@permission_required("programs.change_category", raise_exception=True)
def manage_options(request):
    return render(
        request,
        "programs/options_dashboard.html",
        {
            "categories": Category.objects.all(),
            "communities": Community.objects.all(),
            "source_codes": SourceCode.objects.all(),
            "share_options": ShareOption.objects.all(),
        },
    )


@login_required
@permission_required("programs.change_category", raise_exception=True)
def option_create(request, model_name):
    cfg = MODEL_MAP.get(model_name.lower())
    if not cfg:
        messages.error(request, "Invalid option type.")
        return redirect("manage_options")

    model_cls, form_cls, verbose_name = cfg
    if request.method == "POST":
        form = form_cls(request.POST)
        if form.is_valid():
            inst = form.save()
            log_change(request.user, "Created", inst, {"name": str(inst)})
            messages.success(request, f"{verbose_name} '{inst}' created.")
            return redirect("manage_options")
    else:
        form = form_cls()

    return render(
        request,
        "programs/option_form.html",
        {"form": form, "verbose_name": verbose_name, "action": "Add"},
    )


@login_required
@permission_required("programs.change_category", raise_exception=True)
def option_edit(request, model_name, pk):
    cfg = MODEL_MAP.get(model_name.lower())
    if not cfg:
        messages.error(request, "Invalid option type.")
        return redirect("manage_options")

    model_cls, form_cls, verbose_name = cfg
    instance = get_object_or_404(model_cls, pk=pk)

    if request.method == "POST":
        form = form_cls(request.POST, instance=instance)
        if form.is_valid():
            inst = form.save()
            log_change(request.user, "Updated", inst, {"name": str(inst)})
            messages.success(request, f"{verbose_name} '{inst}' updated.")
            return redirect("manage_options")
    else:
        form = form_cls(instance=instance)

    return render(
        request,
        "programs/option_form.html",
        {"form": form, "verbose_name": verbose_name, "action": "Edit", "instance": instance},
    )


@login_required
@permission_required("programs.change_category", raise_exception=True)
def option_toggle(request, model_name, pk):
    cfg = MODEL_MAP.get(model_name.lower())
    if not cfg:
        messages.error(request, "Invalid option type.")
        return redirect("manage_options")

    model_cls, _, verbose_name = cfg
    instance = get_object_or_404(model_cls, pk=pk)
    instance.is_enabled = not instance.is_enabled
    instance.save()
    status_str = "enabled" if instance.is_enabled else "disabled"
    log_change(request.user, "Updated", instance, {"is_enabled": instance.is_enabled})
    messages.success(request, f"{verbose_name} '{instance}' was {status_str}.")
    return redirect("manage_options")
