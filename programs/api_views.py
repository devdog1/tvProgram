from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from .models import (
    Program,
    Series,
    Category,
    Community,
    SourceCode,
    ShareOption,
    APIKey,
)
from .serializers import (
    ProgramSerializer,
    SeriesSerializer,
    CategorySerializer,
    CommunitySerializer,
    SourceCodeSerializer,
    ShareOptionSerializer,
    APIKeySerializer,
)
from .services import log_change, trigger_event_hooks


class ProgramViewSet(viewsets.ModelViewSet):
    """
    API ViewSet for Programs.

    IMPORTANT:
    By default, this endpoint only returns CURRENT APPROVED programs (status='signed_off').
    Data in a pending approval state (or draft/rejected) is EXCLUDED unless the client
    specifically requests it by providing:
    - ?include_pending=true (or 1, yes)
    - ?status=pending_review (or ?status=all, ?status=draft, etc.)
    """
    queryset = Program.objects.all()
    serializer_class = ProgramSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                description="Filter by specific status ('signed_off', 'pending_review', 'draft', 'rejected', or 'all'). Defaults to 'signed_off'.",
                required=False,
            ),
            OpenApiParameter(
                name="include_pending",
                type=OpenApiTypes.BOOL,
                description="Explicitly include pending approval and unapproved programs. Set to true/1 to include pending review programs.",
                required=False,
            ),
            OpenApiParameter(
                name="category",
                type=OpenApiTypes.STR,
                description="Filter by category slug/name.",
                required=False,
            ),
            OpenApiParameter(
                name="community",
                type=OpenApiTypes.STR,
                description="Filter by community name.",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                description="Search query against title, producer, filename, or comments.",
                required=False,
            ),
        ]
    )
    def get_queryset(self):
        user = self.request.user
        qs = Program.objects.all().select_related("series", "owner_group", "created_by", "signed_off_by")

        # 1. Filter by owner group / permissions
        if not (user.is_superuser or user.has_perm("programs.view_all_programs")):
            qs = qs.filter(Q(owner_group__in=user.groups.all()) | Q(created_by=user)).distinct()

        # 2. Approval status filtering:
        # Prompt requirement: "have the API return the current approved program info,
        # not data in a pending approval state, unless the API specifically call for pending approval state."
        status_param = self.request.query_params.get("status")
        include_pending = self.request.query_params.get("include_pending", "").strip().lower() in ("true", "1", "yes")

        if status_param:
            status_clean = status_param.strip().lower()
            if status_clean != "all":
                qs = qs.filter(status=status_clean)
        elif include_pending:
            # specifically calls for pending approval state included
            pass
        else:
            # Default: only approved (signed_off) programs
            qs = qs.filter(status="signed_off")

        # 3. Additional query filters
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__iexact=category)

        community = self.request.query_params.get("community")
        if community:
            qs = qs.filter(community__icontains=community)

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(producer__icontains=search)
                | Q(filename__icontains=search)
                | Q(comments__icontains=search)
            )

        return qs.order_by("-id")

    def perform_create(self, serializer):
        program = serializer.save(created_by=self.request.user, status="draft")
        log_change(self.request.user, "Created", program, {"source": "API", "title": program.title})
        trigger_event_hooks("program_created", program, self.request.user, details="Created via REST API")

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        # Revert to draft if edited and not draft
        kwargs = {}
        if old_status != "draft":
            kwargs["status"] = "draft"
            kwargs["signed_off_by"] = None
            kwargs["signed_off_at"] = None

        program = serializer.save(**kwargs)
        log_change(self.request.user, "Updated", program, {"source": "API", "title": program.title})
        trigger_event_hooks("program_updated", program, self.request.user, details="Updated via REST API")

    def perform_destroy(self, instance):
        log_change(self.request.user, "Deleted", instance, {"source": "API", "title": instance.title})
        trigger_event_hooks("program_deleted", instance, self.request.user, details="Deleted via REST API")
        instance.delete()


class SeriesViewSet(viewsets.ModelViewSet):
    """
    API ViewSet for TV Series, mini-series, and multi-part productions.
    """
    queryset = Series.objects.all()
    serializer_class = SeriesSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Series.objects.all().select_related("owner_group", "created_by")
        if not (user.is_superuser or user.has_perm("programs.view_all_series")):
            qs = qs.filter(Q(owner_group__in=user.groups.all()) | Q(created_by=user)).distinct()

        status_param = self.request.query_params.get("status")
        if status_param and status_param.lower() != "all":
            qs = qs.filter(status=status_param.lower())

        return qs.order_by("-id")

    def perform_create(self, serializer):
        series = serializer.save(created_by=self.request.user, status="draft")
        log_change(self.request.user, "Created", series, {"source": "API", "title": series.title})

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        kwargs = {}
        if old_status != "draft":
            kwargs["status"] = "draft"
            kwargs["signed_off_by"] = None
            kwargs["signed_off_at"] = None

        series = serializer.save(**kwargs)
        log_change(self.request.user, "Updated", series, {"source": "API", "title": series.title})

    def perform_destroy(self, instance):
        log_change(self.request.user, "Deleted", instance, {"source": "API", "title": instance.title})
        instance.delete()


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API ViewSet for active categories.
    """
    queryset = Category.objects.filter(is_enabled=True)
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class CommunityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API ViewSet for active communities.
    """
    queryset = Community.objects.filter(is_enabled=True)
    serializer_class = CommunitySerializer
    permission_classes = [permissions.IsAuthenticated]


class SourceCodeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API ViewSet for source codes.
    """
    queryset = SourceCode.objects.filter(is_enabled=True)
    serializer_class = SourceCodeSerializer
    permission_classes = [permissions.IsAuthenticated]


class ShareOptionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API ViewSet for share options.
    """
    queryset = ShareOption.objects.filter(is_enabled=True)
    serializer_class = ShareOptionSerializer
    permission_classes = [permissions.IsAuthenticated]


class APIKeyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing API Keys.
    Only administrators can create or manage API keys.
    """
    queryset = APIKey.objects.all()
    serializer_class = APIKeySerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return APIKey.objects.all().select_related("user").order_by("-created_at")

    def create(self, request, *args, **kwargs):
        name = request.data.get("name", "").strip() or f"API Key for {request.user.username}"
        api_key = APIKey.generate_key(user=request.user, name=name)
        serializer = self.get_serializer(api_key)
        # Return full key in create response so client can record it
        data = dict(serializer.data)
        data["key"] = api_key.key
        return Response(data, status=status.HTTP_201_CREATED)
