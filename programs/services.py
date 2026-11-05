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
    - User has change_program permission (e.g. Program Editors / Admins)
    - OR user is the creator of the program (and authenticated)
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm("programs.change_program"):
        return True
    if program.created_by_id and program.created_by_id == user.id:
        return True
    return False


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


def trigger_event_hooks(event_name, instance, user=None, details=""):
    """
    Executes all active event hooks configured for `event_name`.
    e.g. event_name='program_created'
    """
    from django.core.mail import send_mail
    from django.conf import settings
    from django.utils import timezone
    from .models import EventHook
    import urllib.request
    import json

    hooks = EventHook.objects.filter(event_type=event_name, is_active=True)
    if not hooks.exists():
        return

    # Build context dictionary
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

    for hook in hooks:
        try:
            if hook.action_type == "email":
                recipients = hook.recipient_list
                if recipients:
                    subject = (hook.email_subject or "[WCGtv] {event}: {title}").format(**context)
                    body = (hook.email_body or "Event: {event}\nTitle: {title}").format(**context)
                    send_mail(
                        subject=subject,
                        message=body,
                        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@wcgtv.local"),
                        recipient_list=recipients,
                        fail_silently=True,
                    )
            elif hook.action_type == "webhook" and hook.webhook_url:
                payload = json.dumps(context).encode("utf-8")
                headers = {"Content-Type": "application/json"}
                if hook.webhook_secret:
                    headers["X-WCGtv-Secret"] = hook.webhook_secret
                req = urllib.request.Request(hook.webhook_url, data=payload, headers=headers, method="POST")
                try:
                    urllib.request.urlopen(req, timeout=5)
                except Exception:
                    pass

            hook.last_triggered_at = timezone.now()
            hook.save(update_fields=["last_triggered_at"])
        except Exception:
            pass
