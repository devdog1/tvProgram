import json
from django.core.serializers.json import DjangoJSONEncoder
from .models import ChangeLog


def log_change(user, action, instance, changes_dict=None):
    """
    Records an entry in the ChangeLog table.
    """
    user_display = "System"
    if user and user.is_authenticated:
        user_display = user.username

    details_str = ""
    if changes_dict:
        details_str = json.dumps(changes_dict, cls=DjangoJSONEncoder)

    object_repr = str(instance)[:255]
    object_type = instance.__class__.__name__

    return ChangeLog.objects.create(
        user=user if (user and user.is_authenticated) else None,
        user_display=user_display,
        action=action,
        object_type=object_type,
        object_id=str(getattr(instance, "id", getattr(instance, "pk", ""))),
        object_repr=object_repr,
        details=details_str,
    )


def can_edit_program(user, program):
    """
    Checks if a user can edit a program:
    - User is superuser or has change_program permission (e.g. Program Editors / Admins)
    - OR user is a member of the owner_group of the program
    - OR user is the creator of the program
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm("programs.change_program"):
        return True
    if program.owner_group_id and user.groups.filter(id=program.owner_group_id).exists():
        return True
    if program.created_by_id and program.created_by_id == user.id:
        return True
    return False


def can_edit_series(user, series):
    """
    Checks if a user can edit a series:
    - User is superuser or has change_series permission
    - OR user is a member of the owner_group of the series
    - OR user is the creator of the series
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm("programs.change_series"):
        return True
    if series.owner_group_id and user.groups.filter(id=series.owner_group_id).exists():
        return True
    if series.created_by_id and series.created_by_id == user.id:
        return True
    return False


def user_can_view_all_programs(user):
    """Checks if the user has global permission to view all programs."""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.has_perm("programs.view_all_programs")


def user_can_view_all_series(user):
    """Checks if the user has global permission to view all series."""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.has_perm("programs.view_all_series")


def can_delete_program(user, program):
    """
    Checks if a user can delete a program:
    - User has delete_program permission (Admins / Program Editors with delete permission)
    - Note: The requirement specifies "The user who added the program may edit it (cannot delete)"
      so being the creator alone DOES NOT give delete permission.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm("programs.delete_program"):
        return True
    return False


def can_sign_off(user):
    """
    Sign-off / approval permission:
    - Admins, superusers, or users with change_program permission / signoff role.
    """
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.has_perm("programs.change_program")


def send_wcgtv_email(subject, body, recipients, fail_silently=True):
    """
    Sends email using configured SMTPSettings relay and envelope from (Return-Path).
    If custom SMTP relay connection fails (or host unreachable), falls back cleanly
    to Django's configured default backend (e.g. console/locmem) so messages are never lost.
    """
    import logging
    from django.core.mail import EmailMessage
    from django.core.mail.backends.smtp import EmailBackend
    from django.conf import settings
    from .models import SMTPSettings
    import smtplib

    logger = logging.getLogger("programs")

    if not recipients:
        return 0

    smtp_config = SMTPSettings.get_settings()
    from_addr = smtp_config.from_address or getattr(settings, "DEFAULT_FROM_EMAIL", "wcgtv@wcgtv.local")
    envelope_from = smtp_config.get_envelope_from() or from_addr

    headers = {
        "Return-Path": envelope_from,
        "Sender": envelope_from,
        "X-Envelope-From": envelope_from,
    }

    # If custom SMTP relay settings are active and not in locmem test backend mode
    is_locmem_test = (getattr(settings, "EMAIL_BACKEND", "") == "django.core.mail.backends.locmem.EmailBackend")

    if smtp_config and smtp_config.is_active and not is_locmem_test:
        # Utilize django-smtp-ssl or Django's EmailBackend depending on SSL requirements
        from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend
        try:
            from django_smtp_ssl import SSLEmailBackend
        except ImportError:
            SSLEmailBackend = DjangoSMTPBackend

        base_backend = SSLEmailBackend if (smtp_config.use_ssl and not smtp_config.use_tls) else DjangoSMTPBackend

        class PostfixEnvelopeSMTPBackend(base_backend):
            def _send(self, email_message):
                if not email_message.recipients():
                    return False
                from_email = self.prep_address(envelope_from)
                recips = [self.prep_address(addr) for addr in email_message.recipients()]
                message = email_message.message()
                try:
                    self.connection.sendmail(from_email, recips, message.as_bytes())
                except smtplib.SMTPException as exc:
                    logger.warning("SMTP sendmail error: %s", exc)
                    if not self.fail_silently:
                        raise
                    return False
                return True

        try:
            backend_kwargs = {
                "host": smtp_config.host,
                "port": smtp_config.port,
                "username": smtp_config.username or None,
                "password": smtp_config.password or None,
                "timeout": smtp_config.timeout,
                "fail_silently": False,
            }
            if base_backend == DjangoSMTPBackend:
                backend_kwargs["use_tls"] = smtp_config.use_tls
                backend_kwargs["use_ssl"] = smtp_config.use_ssl

            custom_connection = PostfixEnvelopeSMTPBackend(**backend_kwargs)
            msg = EmailMessage(
                subject=subject,
                body=body,
                from_email=from_addr,
                to=recipients,
                headers=headers,
                connection=custom_connection,
            )
            sent = msg.send(fail_silently=False)
            if sent:
                return sent
        except Exception as exc:
            logger.warning(
                "Custom SMTP relay (%s:%s) failed with %s: %s. Falling back to default Django backend.",
                smtp_config.host,
                smtp_config.port,
                type(exc).__name__,
                exc,
            )
            if not fail_silently and is_locmem_test:
                raise

    # Fallback to standard Django default connection (console / settings backend)
    try:
        fallback_msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_addr,
            to=recipients,
            headers=headers,
        )
        return fallback_msg.send(fail_silently=fail_silently)
    except Exception as exc:
        logger.error("Failed to send email via fallback backend: %s", exc)
        if not fail_silently:
            raise
        return 0


def trigger_event_hooks(event_name, instance, user=None, details=""):
    """
    Executes all active event hooks configured for `event_name`.
    e.g. event_name='program_created'
    """
    import logging
    from django.utils import timezone
    from .models import EventHook
    import urllib.request
    import json

    logger = logging.getLogger("programs")
    hooks = EventHook.objects.filter(event_type=event_name, is_active=True)
    if not hooks.exists():
        return

    # Build context dictionary with fallback for missing attributes
    title = getattr(instance, "title", str(instance))
    obj_id = getattr(instance, "id", "")
    producer = getattr(instance, "producer", "")
    user_display = user.username if (user and user.is_authenticated) else "System"

    context = {
        "event": event_name,
        "title": title,
        "id": obj_id,
        "producer": producer,
        "user": user_display,
        "details": details or "",
    }

    class SafeDict(dict):
        def __missing__(self, key):
            return f"{{{key}}}"

    safe_context = SafeDict(context)

    for hook in hooks:
        try:
            if hook.action_type == "email":
                recipients = hook.recipient_list
                if recipients:
                    subject_tmpl = hook.email_subject or "[WCGtv] {event}: {title}"
                    body_tmpl = hook.email_body or "Event: {event}\nTitle: {title}"
                    try:
                        subject = subject_tmpl.format_map(safe_context)
                    except Exception:
                        subject = f"[WCGtv] {event_name}: {title}"
                    try:
                        body = body_tmpl.format_map(safe_context)
                    except Exception:
                        body = f"Event: {event_name}\nTitle: {title}\nDetails: {details}"

                    sent_count = send_wcgtv_email(
                        subject=subject,
                        body=body,
                        recipients=recipients,
                        fail_silently=True,
                    )
                    logger.info(
                        "Dispatched email hook '%s' for event '%s' (title: %s) to %d recipient(s): %s",
                        hook.name,
                        event_name,
                        title,
                        len(recipients),
                        ", ".join(recipients),
                    )
                    log_change(
                        user=user,
                        action="Dispatched Email",
                        instance=instance,
                        changes_dict={
                            "hook_name": hook.name,
                            "event": event_name,
                            "recipients": recipients,
                            "subject": subject,
                            "sent": bool(sent_count),
                        },
                    )
            elif hook.action_type == "webhook" and hook.webhook_url:
                payload = json.dumps(context).encode("utf-8")
                headers = {"Content-Type": "application/json"}
                if hook.webhook_secret:
                    headers["X-WCGtv-Secret"] = hook.webhook_secret
                req = urllib.request.Request(hook.webhook_url, data=payload, headers=headers, method="POST")
                status_code = None
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        status_code = resp.getcode()
                    logger.info(
                        "Dispatched webhook hook '%s' for event '%s' to %s (HTTP %s)",
                        hook.name,
                        event_name,
                        hook.webhook_url,
                        status_code,
                    )
                except Exception as w_exc:
                    logger.warning("Webhook request failed for %s: %s", hook.webhook_url, w_exc)
                    status_code = f"Error: {w_exc}"

                log_change(
                    user=user,
                    action="Dispatched Webhook",
                    instance=instance,
                    changes_dict={
                        "hook_name": hook.name,
                        "event": event_name,
                        "webhook_url": hook.webhook_url,
                        "status": str(status_code),
                    },
                )

            hook.last_triggered_at = timezone.now()
            hook.save(update_fields=["last_triggered_at"])
        except Exception as e:
            logger.error("Error executing hook '%s': %s", hook.name, e)


def process_bulk_program_csv(csv_content, user=None, preserve_ids=False, skip_errors=True):
    """
    Parses and imports programs from CSV text.
    Handles columns matching PHP index/database:
    id, created, title, dateRecorded, expiryDate, producer, length, category,
    community, sourceCode, share, filename, comments
    """
    import csv
    import io
    import re
    from datetime import datetime
    from django.utils import timezone
    from django.db import transaction
    from .models import Program

    reader = csv.DictReader(io.StringIO(csv_content))
    # Normalize headers by stripping whitespace and lowercasing for lookup
    if not reader.fieldnames:
        return {"success": False, "imported": 0, "errors": ["CSV content is empty or has no header row."]}

    # Map normalized header name to original field name
    header_map = {fn.strip().lower(): fn for fn in reader.fieldnames if fn}

    def get_val(row, *aliases):
        for alias in aliases:
            low = alias.lower()
            if low in header_map:
                actual_key = header_map[low]
                val = row.get(actual_key)
                if val is not None:
                    return str(val).strip()
        return ""

    time_regex = re.compile(r"^\d{2}:\d{2}:\d{2}$")
    filename_regex = re.compile(r'^[^\\/:*?"<>|]+\.[a-zA-Z0-9]{1,5}$')
    date_regex = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    imported_programs = []
    errors = []
    row_number = 1  # 1 is header

    for row in reader:
        row_number += 1
        # Skip completely empty rows
        if not any(v.strip() for v in row.values() if v):
            continue

        row_errors = []
        raw_id = get_val(row, "id")
        raw_created = get_val(row, "created", "created_at")
        title = get_val(row, "title")
        date_recorded_str = get_val(row, "dateRecorded", "date_recorded", "recorded_date")
        expiry_date_str = get_val(row, "expiryDate", "expiry_date")
        producer = get_val(row, "producer")
        length = get_val(row, "length", "duration")
        category = get_val(row, "category")
        community = get_val(row, "community")
        source_code = get_val(row, "sourceCode", "source_code")
        share = get_val(row, "share", "share_with")
        filename = get_val(row, "filename")
        comments = get_val(row, "comments", "notes")

        # Validation checks
        if not title:
            row_errors.append("Title is required.")
        if not producer:
            row_errors.append("Producer is required.")

        # Date recorded
        date_recorded = None
        if not date_recorded_str:
            row_errors.append("Date Recorded is required.")
        else:
            # Handle YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            date_match = date_regex.match(date_recorded_str[:10])
            if not date_match:
                row_errors.append(f"Invalid Date Recorded '{date_recorded_str}'. Expected YYYY-MM-DD.")
            else:
                try:
                    date_recorded = datetime.strptime(date_recorded_str[:10], "%Y-%m-%d").date()
                except ValueError:
                    row_errors.append(f"Invalid Date Recorded date value '{date_recorded_str}'.")

        # Expiry date
        expiry_date = None
        if expiry_date_str:
            date_match = date_regex.match(expiry_date_str[:10])
            if not date_match:
                row_errors.append(f"Invalid Expiry Date '{expiry_date_str}'. Expected YYYY-MM-DD.")
            else:
                try:
                    expiry_date = datetime.strptime(expiry_date_str[:10], "%Y-%m-%d").date()
                except ValueError:
                    row_errors.append(f"Invalid Expiry Date date value '{expiry_date_str}'.")

        # Length validation
        if not length:
            row_errors.append("Length is required.")
        elif not time_regex.match(length):
            row_errors.append(f"Invalid length '{length}'. Must be in HH:MM:SS format.")

        # Filename validation
        if not filename:
            row_errors.append("Filename is required.")
        elif not filename_regex.match(filename):
            row_errors.append(f"Invalid filename '{filename}'. Must be valid with an extension (e.g. myfile.mp4).")

        # Comments validation
        if len(comments) > 255:
            row_errors.append(f"Comments too long ({len(comments)} chars, max 255).")

        if row_errors:
            errors.append(f"Row {row_number}: " + "; ".join(row_errors))
            if not skip_errors:
                return {
                    "success": False,
                    "imported": 0,
                    "errors": errors,
                }
            continue

        # Create program object
        program = Program(
            title=title,
            date_recorded=date_recorded,
            expiry_date=expiry_date,
            producer=producer,
            length=length,
            category=category,
            community=community,
            source_code=source_code,
            share=share,
            filename=filename,
            comments=comments,
            created_by=user if (user and user.is_authenticated) else None,
            status="draft",
        )

        # Handle ID preservation
        if preserve_ids and raw_id and raw_id.isdigit():
            req_id = int(raw_id)
            if not Program.objects.filter(id=req_id).exists():
                program.id = req_id

        # Handle created date if provided
        created_dt = None
        if raw_created:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    created_dt = datetime.strptime(raw_created, fmt)
                    if timezone.is_naive(created_dt):
                        created_dt = timezone.make_aware(created_dt)
                    break
                except ValueError:
                    pass

        try:
            program.save()
            if created_dt:
                Program.objects.filter(pk=program.pk).update(created=created_dt)

            log_change(
                user,
                "Created",
                program,
                changes_dict={"source": "Bulk CSV Import", "row": row_number, "filename": filename},
            )
            trigger_event_hooks("program_created", program, user, details="Created via Bulk CSV Import")
            imported_programs.append(program)
        except Exception as e:
            err_msg = f"Row {row_number} (Title: '{title}'): Failed to save - {str(e)}"
            errors.append(err_msg)
            if not skip_errors:
                return {
                    "success": False,
                    "imported": 0,
                    "errors": errors,
                }

    return {
        "success": len(imported_programs) > 0 or len(errors) == 0,
        "imported": len(imported_programs),
        "imported_programs": imported_programs,
        "errors": errors,
    }
