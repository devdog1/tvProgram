from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.utils import timezone
from .models import APIKey


class APIKeyAuthentication(BaseAuthentication):
    """
    Custom DRF Authentication scheme that validates API Keys provided via:
    1. HTTP header `X-API-Key: <key>`
    2. HTTP header `Authorization: Api-Key <key>`
    """

    def authenticate(self, request):
        api_key_str = None

        # Check X-API-Key header
        if "HTTP_X_API_KEY" in request.META:
            api_key_str = request.META["HTTP_X_API_KEY"]

        # Check Authorization header (Api-Key <key>)
        if not api_key_str and "HTTP_AUTHORIZATION" in request.META:
            auth_header = request.META["HTTP_AUTHORIZATION"].strip()
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() in ("api-key", "apikey", "bearer", "token"):
                api_key_str = parts[1]

        if not api_key_str:
            return None  # Fall back to other authentication classes (e.g. SessionAuthentication)

        try:
            api_key = APIKey.objects.select_related("user").get(key=api_key_str, is_active=True)
        except APIKey.DoesNotExist:
            raise AuthenticationFailed("Invalid or inactive API Key.")

        if not api_key.user.is_active:
            raise AuthenticationFailed("User linked to this API Key is disabled.")

        # Update last_used_at timestamp
        APIKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())

        return (api_key.user, api_key)
