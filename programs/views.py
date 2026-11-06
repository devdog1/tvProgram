from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse
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
    SMTPSettings,
    APIKey,
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
    BulkProgramImportForm,
    SMTPSettingsForm,
)
from .services import (
    log_change,
    can_edit_program,
    can_edit_series,
    can_delete_program,
    can_sign_off,
    trigger_event_hooks,
    process_bulk_program_csv,
    user_can_view_all_programs,
    user_can_view_all_series,
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
    """
    Optimized program listing view capable of handling many 10,000s of programs.
    By default only shows programs that the user is a member of the owner user group,
    unless the user has the 'view_all_programs' permission (or is superuser).
    """
    qs = Program.objects.select_related("series", "created_by", "owner_group")

    if not user_can_view_all_programs(request.user):
        user_groups = request.user.groups.all()
        # Filter by owner_group in user's groups OR programs created by this user
        qs = qs.filter(Q(owner_group__in=user_groups) | Q(created_by=request.user))

    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    category_filter = request.GET.get("category", "").strip()
    community_filter = request.GET.get("community", "").strip()
    source_code_filter = request.GET.get("source_code", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    sort_by = request.GET.get("sort", "-id")

    # Allowed sorting fields
    allowed_sorts = {
        "-id": "-id",
        "id": "id",
        "title": "title",
        "-title": "-title",
        "date_recorded": "date_recorded",
        "-date_recorded": "-date_recorded",
        "producer": "producer",
        "-producer": "-producer",
        "category": "category",
        "-category": "-category",
        "status": "status",
        "-status": "-status",
    }
    order_field = allowed_sorts.get(sort_by, "-id")

    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(producer__icontains=q)
            | Q(filename__icontains=q)
            | Q(comments__icontains=q)
            | Q(community__icontains=q)
            | Q(source_code__icontains=q)
            | Q(series__title__icontains=q)
        )

    if status_filter:
        qs = qs.filter(status=status_filter)

    if category_filter:
        qs = qs.filter(category=category_filter)

    if community_filter:
        qs = qs.filter(community__icontains=community_filter)

    if source_code_filter:
        qs = qs.filter(source_code=source_code_filter)

    if date_from:
        qs = qs.filter(date_recorded__gte=date_from)

    if date_to:
        qs = qs.filter(date_recorded__lte=date_to)

    qs = qs.order_by(order_field)

    # Pagination: default 50 items per page (customizable via per_page param: 25, 50, 100, 200)
    per_page_param = request.GET.get("per_page", "50")
    try:
        per_page = int(per_page_param)
        if per_page not in [25, 50, 100, 200]:
            per_page = 50
    except (ValueError, TypeError):
        per_page = 50

    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page", 1)

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    # Annotate only the current page's slice (e.g. 50 items instead of 100,000!)
    is_admin_or_editor = request.user.is_superuser or request.user.has_perm("programs.change_program")
    can_del_globally = request.user.is_superuser or request.user.has_perm("programs.delete_program")
    user_groups_set = set(request.user.groups.values_list("id", flat=True))
    user_id = request.user.id

    for p in page_obj.object_list:
        p.user_can_edit = (
            is_admin_or_editor
            or (p.created_by_id == user_id)
            or (p.owner_group_id and p.owner_group_id in user_groups_set)
        )
        p.user_can_delete = can_del_globally

    categories = Category.objects.filter(is_enabled=True)
    communities = Community.objects.filter(is_enabled=True)
    source_codes = SourceCode.objects.filter(is_enabled=True)

    # Build querystring without page for pagination links
    query_params = request.GET.copy()
    query_params.pop("page", None)
    filter_querystring = query_params.urlencode()

    has_active_filters = bool(
        q or status_filter or category_filter or community_filter or source_code_filter or date_from or date_to or (sort_by != "-id")
    )

    return render(
        request,
        "programs/program_list.html",
        {
            "page_obj": page_obj,
            "programs": page_obj.object_list,
            "total_count": paginator.count,
            "categories": categories,
            "communities": communities,
            "source_codes": source_codes,
            "current_sort": sort_by,
            "current_q": q,
            "current_status": status_filter,
            "current_category": category_filter,
            "current_community": community_filter,
            "current_source_code": source_code_filter,
            "current_date_from": date_from,
            "current_date_to": date_to,
            "per_page": per_page,
            "filter_querystring": filter_querystring,
            "has_active_filters": has_active_filters,
        },
    )


@login_required
def program_detail(request, pk):
    program = get_object_or_404(
        Program.objects.select_related("series", "created_by", "signed_off_by", "owner_group").prefetch_related("attachments"),
        pk=pk,
    )

    # Permission check for viewing: if not superuser / view_all_programs, must be in owner_group or creator
    if not user_can_view_all_programs(request.user):
        if not (
            (program.owner_group and request.user.groups.filter(id=program.owner_group.id).exists())
            or (program.created_by_id == request.user.id)
        ):
            raise PermissionDenied("You do not have permission to view this program.")
    user_can_edit = can_edit_program(request.user, program)
    user_can_delete = can_delete_program(request.user, program)
    user_can_approve = can_sign_off(request.user)

    # Custom fields data for Program target element
    active_custom_fields = CustomField.objects.filter(is_active=True, target_element="program")
    existing_val_objs = {v.custom_field_id: v for v in program.custom_field_values.all()}
    custom_fields_data = []
    for f in active_custom_fields:
        val_obj = existing_val_objs.get(f.id)
        val_str = ""
        file_url = ""
        if val_obj:
            val_str = val_obj.value or (val_obj.file_upload.name.split("/")[-1] if val_obj.file_upload else "")
            if val_obj.file_upload:
                file_url = val_obj.file_upload.url
        else:
            val_str = f.default_value or ""
        custom_fields_data.append({"field": f, "value": val_str, "file_url": file_url})

    # Fetch ChangeLog entries for this specific program
    change_logs = ChangeLog.objects.filter(
        object_type="Program",
        object_id=str(program.id),
    ).order_by("-timestamp")

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
            "change_logs": change_logs,
        },
    )


@login_required
@permission_required("programs.add_program", raise_exception=True)
def program_create(request):
    active_custom_fields = CustomField.objects.filter(is_active=True, target_element="program")

    if request.method == "POST":
        form = ProgramForm(request.POST, user=request.user)
        if form.is_valid():
            program = form.save(commit=False)
            program.created_by = request.user
            program.save()

            # Save custom fields
            for cf in active_custom_fields:
                if cf.field_type == "file":
                    file_obj = request.FILES.get(f"custom_field_{cf.name}")
                    if file_obj:
                        CustomFieldValue.objects.create(
                            program=program,
                            custom_field=cf,
                            file_upload=file_obj,
                            value=file_obj.name,
                        )
                else:
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
        form = ProgramForm(initial=initial, user=request.user)

    custom_field_inputs = [
        {"field": cf, "value": cf.default_value or "", "file_url": ""}
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

    active_custom_fields = CustomField.objects.filter(is_active=True, target_element="program")
    existing_values_map = {
        cfv.custom_field_id: cfv for cfv in program.custom_field_values.all()
    }

    if request.method == "POST":
        form = ProgramForm(request.POST, instance=program, user=request.user)
        if form.is_valid():
            # If there is an edit, move the program back to draft state,
            # and have to redo the sign-off process
            was_already_signed_off_or_pending = program.status != "draft"
            updated_program = form.save(commit=False)
            if was_already_signed_off_or_pending:
                updated_program.status = "draft"
                updated_program.signed_off_by = None
                updated_program.signed_off_at = None
                updated_program.sign_off_notes = f"Reset to draft on edit by {request.user.username}. Needs new sign-off."
            updated_program.save()

            # Handle custom fields update
            changes_cf = {}
            for cf in active_custom_fields:
                if cf.field_type == "file":
                    file_obj = request.FILES.get(f"custom_field_{cf.name}")
                    if file_obj:
                        cfv = existing_values_map.get(cf.id)
                        if cfv:
                            cfv.file_upload = file_obj
                            cfv.value = file_obj.name
                            cfv.save()
                        else:
                            CustomFieldValue.objects.create(
                                program=updated_program,
                                custom_field=cf,
                                file_upload=file_obj,
                                value=file_obj.name,
                            )
                        changes_cf[cf.label] = f"Updated file: {file_obj.name}"
                else:
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
        form = ProgramForm(instance=program, user=request.user)

    custom_field_inputs = []
    for cf in active_custom_fields:
        cfv = existing_values_map.get(cf.id)
        val = cfv.value if cfv else (cf.default_value or "")
        f_url = cfv.file_upload.url if (cfv and cfv.file_upload) else ""
        custom_field_inputs.append({"field": cf, "value": val, "file_url": f_url})

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
@permission_required("programs.can_bulk_import", raise_exception=True)
def program_bulk_import(request):
    """
    Bulk CSV Import View for Programs.
    Supports CSV file upload or direct text paste.
    Requires dedicated programs.can_bulk_import permission.
    """
    results = None
    if request.method == "POST":
        form = BulkProgramImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = form.cleaned_data.get("csv_file")
            csv_text = form.cleaned_data.get("csv_text")
            preserve_ids = form.cleaned_data.get("preserve_ids")
            skip_errors = form.cleaned_data.get("skip_errors")

            content = ""
            if csv_file:
                content = csv_file.read().decode("utf-8-sig", errors="replace")
            elif csv_text:
                content = csv_text

            results = process_bulk_program_csv(
                csv_content=content,
                user=request.user,
                preserve_ids=preserve_ids,
                skip_errors=skip_errors,
            )

            if results["imported"] > 0:
                messages.success(request, f"Successfully imported {results['imported']} program(s).")
            if results["errors"]:
                if results["imported"] == 0:
                    messages.error(request, f"Import failed with {len(results['errors'])} error(s).")
                else:
                    messages.warning(request, f"Completed with {len(results['errors'])} issue(s) encountered.")
    else:
        sample_csv = (
            'id,created,title,dateRecorded,expiryDate,producer,length,category,community,sourceCode,share,filename,comments\n'
            '1,"2015-03-10 16:47:28",Sample Program 1,2015-02-02,,fred,01:02:03,sports,"Brandon,Carberry",a - Single Camera/No Editing,All,sample1.mp4,First imported program\n'
            '2,"2015-03-10 16:55:48",Sample Program 2,2015-03-11,,fred,01:02:03,sports,,,All,sample2.mp4,'
        )
        form = BulkProgramImportForm(initial={"csv_text": sample_csv})

    return render(
        request,
        "programs/program_bulk_import.html",
        {"form": form, "results": results},
    )


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
    qs = Series.objects.prefetch_related("episodes").select_related("created_by", "owner_group")
    if not user_can_view_all_series(request.user):
        user_groups = request.user.groups.all()
        qs = qs.filter(Q(owner_group__in=user_groups) | Q(created_by=request.user))
    return render(request, "programs/series_list.html", {"series_list": qs})


@login_required
def series_detail(request, pk):
    series = get_object_or_404(Series.objects.prefetch_related("episodes").select_related("created_by", "signed_off_by", "owner_group"), pk=pk)
    if not user_can_view_all_series(request.user):
        if not (
            (series.owner_group and request.user.groups.filter(id=series.owner_group.id).exists())
            or (series.created_by_id == request.user.id)
        ):
            raise PermissionDenied("You do not have permission to view this series.")

    user_can_approve = can_sign_off(request.user)

    # Custom fields data for Series target element
    active_custom_fields = CustomField.objects.filter(is_active=True, target_element="series")
    existing_val_objs = {v.custom_field_id: v for v in series.custom_field_values.all()}
    custom_fields_data = []
    for f in active_custom_fields:
        val_obj = existing_val_objs.get(f.id)
        val_str = ""
        file_url = ""
        if val_obj:
            val_str = val_obj.value or (val_obj.file_upload.name.split("/")[-1] if val_obj.file_upload else "")
            if val_obj.file_upload:
                file_url = val_obj.file_upload.url
        else:
            val_str = f.default_value or ""
        custom_fields_data.append({"field": f, "value": val_str, "file_url": file_url})

    return render(
        request,
        "programs/series_detail.html",
        {"series": series, "user_can_approve": user_can_approve, "custom_fields_data": custom_fields_data},
    )


@login_required
def series_create(request):
    active_custom_fields = CustomField.objects.filter(is_active=True, target_element="series")
    if request.method == "POST":
        form = SeriesForm(request.POST, user=request.user)
        if form.is_valid():
            series = form.save(commit=False)
            series.created_by = request.user
            series.save()

            # Save series custom fields
            for cf in active_custom_fields:
                if cf.field_type == "file":
                    file_obj = request.FILES.get(f"custom_field_{cf.name}")
                    if file_obj:
                        CustomFieldValue.objects.create(
                            series=series,
                            custom_field=cf,
                            file_upload=file_obj,
                            value=file_obj.name,
                        )
                else:
                    val = request.POST.get(f"custom_field_{cf.name}", "").strip()
                    if val:
                        CustomFieldValue.objects.create(series=series, custom_field=cf, value=val)

            log_change(request.user, "Created", series, {"title": series.title, "type": series.series_type})
            messages.success(request, f"Series '{series.title}' created.")
            return redirect("series_detail", pk=series.pk)
    else:
        form = SeriesForm(user=request.user)

    custom_field_inputs = [
        {"field": cf, "value": cf.default_value or "", "file_url": ""}
        for cf in active_custom_fields
    ]
    return render(request, "programs/series_form.html", {"form": form, "custom_field_inputs": custom_field_inputs})


@login_required
def series_edit(request, pk):
    series = get_object_or_404(Series, pk=pk)
    if not can_edit_series(request.user, series):
        raise PermissionDenied("You do not have permission to edit this series.")

    active_custom_fields = CustomField.objects.filter(is_active=True, target_element="series")
    existing_values_map = {
        cfv.custom_field_id: cfv for cfv in series.custom_field_values.all()
    }

    if request.method == "POST":
        form = SeriesForm(request.POST, instance=series, user=request.user)
        if form.is_valid():
            # If there is an edit, move the series back to draft state,
            # and have to redo the sign-off process
            was_already_signed_off_or_pending = series.status != "draft"
            s = form.save(commit=False)
            if was_already_signed_off_or_pending:
                s.status = "draft"
                s.signed_off_by = None
                s.signed_off_at = None
                s.sign_off_notes = f"Reset to draft on edit by {request.user.username}. Needs new sign-off."
            s.save()

            # Handle series custom fields update
            changes_cf = {}
            for cf in active_custom_fields:
                if cf.field_type == "file":
                    file_obj = request.FILES.get(f"custom_field_{cf.name}")
                    if file_obj:
                        cfv = existing_values_map.get(cf.id)
                        if cfv:
                            cfv.file_upload = file_obj
                            cfv.value = file_obj.name
                            cfv.save()
                        else:
                            CustomFieldValue.objects.create(
                                series=s,
                                custom_field=cf,
                                file_upload=file_obj,
                                value=file_obj.name,
                            )
                        changes_cf[cf.label] = f"Updated file: {file_obj.name}"
                else:
                    new_val = request.POST.get(f"custom_field_{cf.name}", "").strip()
                    cfv = existing_values_map.get(cf.id)
                    if cfv:
                        if cfv.value != new_val:
                            changes_cf[cf.label] = {"from": cfv.value, "to": new_val}
                            cfv.value = new_val
                            cfv.save()
                    elif new_val:
                        CustomFieldValue.objects.create(series=s, custom_field=cf, value=new_val)
                        changes_cf[cf.label] = {"from": "", "to": new_val}

            log_change(request.user, "Updated", s, {"changed": form.changed_data, "custom_fields": changes_cf})
            messages.success(request, f"Series '{s.title}' updated.")
            return redirect("series_detail", pk=s.pk)
    else:
        form = SeriesForm(instance=series, user=request.user)

    custom_field_inputs = []
    for cf in active_custom_fields:
        cfv = existing_values_map.get(cf.id)
        val = cfv.value if cfv else (cf.default_value or "")
        f_url = cfv.file_upload.url if (cfv and cfv.file_upload) else ""
        custom_field_inputs.append({"field": cf, "value": val, "file_url": f_url})

    return render(request, "programs/series_form.html", {"form": form, "custom_field_inputs": custom_field_inputs})


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
    """
    Validation queue for pending programs and series.
    By default, only displays items owned by the user's groups or created by the user,
    unless the user possesses 'view_all_programs' / 'view_all_series' permissions.
    """
    user = request.user
    user_groups = user.groups.all()

    # Filter programs
    pending_programs = Program.objects.filter(status="pending_review").select_related("series", "created_by", "owner_group")
    if not (user.is_superuser or user.has_perm("programs.view_all_programs")):
        pending_programs = pending_programs.filter(
            Q(owner_group__in=user_groups) | Q(created_by=user)
        ).distinct()

    # Filter series
    pending_series = Series.objects.filter(status="pending_review").select_related("created_by", "owner_group")
    if not (user.is_superuser or user.has_perm("programs.view_all_series")):
        pending_series = pending_series.filter(
            Q(owner_group__in=user_groups) | Q(created_by=user)
        ).distinct()

    is_filtered = not (
        (user.is_superuser or user.has_perm("programs.view_all_programs"))
        and (user.is_superuser or user.has_perm("programs.view_all_series"))
    )

    return render(
        request,
        "programs/signoff_queue.html",
        {
            "pending_programs": pending_programs,
            "pending_series": pending_series,
            "is_filtered": is_filtered,
        },
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


# ==============================================================================
# SMTP Relay Settings View
# ==============================================================================

@login_required
def smtp_settings_view(request):
    """
    Admin configuration for SMTP relay server, sender From address,
    and Postfix envelope from (Return-Path).
    """
    if not (request.user.is_staff or request.user.is_superuser or request.user.has_perm("programs.change_smtpsettings")):
        raise PermissionDenied("You do not have permission to configure SMTP settings.")

    instance = SMTPSettings.objects.first()
    if not instance:
        instance = SMTPSettings.objects.create(
            host="localhost",
            port=25,
            from_address="wcgtv@wcgtv.local",
            envelope_from="wcgtv@wcgtv.local",
            is_active=True,
        )

    if request.method == "POST":
        form = SMTPSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            saved_settings = form.save()
            log_change(
                request.user,
                "Updated",
                saved_settings,
                {
                    "host": saved_settings.host,
                    "port": saved_settings.port,
                    "from_address": saved_settings.from_address,
                    "envelope_from": saved_settings.get_envelope_from(),
                    "is_active": saved_settings.is_active,
                },
            )
            messages.success(request, "SMTP relay settings and Postfix envelope sender updated successfully.")
            return redirect("smtp_settings")
    else:
        form = SMTPSettingsForm(instance=instance)

    return render(
        request,
        "programs/smtp_settings.html",
        {"form": form, "settings_obj": instance},
    )


# ==============================================================================
# API Key Management Views (Admins only)
# ==============================================================================

@login_required
def api_keys_view(request):
    """
    View and generate API keys for automated integrations.
    Strictly restricted to administrators.
    """
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("Only administrators can manage API keys.")

    new_key = None
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            api_key_obj = APIKey.generate_key(user=request.user, name=name)
            new_key = api_key_obj.key
            log_change(request.user, "Created", api_key_obj, {"name": name, "prefix": api_key_obj.prefix})
            messages.success(request, f"Generated API Key '{name}'.")
        else:
            messages.error(request, "Key Name is required.")

    keys = APIKey.objects.all().select_related("user")

    return render(
        request,
        "programs/api_keys.html",
        {"api_keys": keys, "new_key": new_key},
    )


@login_required
def api_key_toggle(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("Only administrators can manage API keys.")

    key_obj = get_object_or_404(APIKey, pk=pk)
    if request.method == "POST":
        key_obj.is_active = not key_obj.is_active
        key_obj.save()
        status_str = "enabled" if key_obj.is_active else "disabled"
        log_change(request.user, "Updated", key_obj, {"is_active": key_obj.is_active})
        messages.success(request, f"API key '{key_obj.name}' was {status_str}.")

    return redirect("api_keys_view")


@login_required
def api_key_delete(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("Only administrators can manage API keys.")

    key_obj = get_object_or_404(APIKey, pk=pk)
    if request.method == "POST":
        name = key_obj.name
        log_change(request.user, "Deleted", key_obj, {"name": name})
        key_obj.delete()
        messages.success(request, f"API key '{name}' was revoked and removed.")

    return redirect("api_keys_view")
