from drf_spectacular.extensions import OpenApiAuthenticationExtension


class APIKeyScheme(OpenApiAuthenticationExtension):
    target_class = "programs.authentication.APIKeyAuthentication"
    name = "ApiKeyAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "Enter your API key formatted as 'wcgtv_...'. You can also pass 'Authorization: Api-Key <key>'.",
        }
