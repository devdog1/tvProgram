from rest_framework.routers import DefaultRouter
from .api_views import (
    ProgramViewSet,
    SeriesViewSet,
    CategoryViewSet,
    CommunityViewSet,
    SourceCodeViewSet,
    ShareOptionViewSet,
    APIKeyViewSet,
)

router = DefaultRouter()
router.register(r"programs", ProgramViewSet, basename="api-programs")
router.register(r"series", SeriesViewSet, basename="api-series")
router.register(r"categories", CategoryViewSet, basename="api-categories")
router.register(r"communities", CommunityViewSet, basename="api-communities")
router.register(r"source-codes", SourceCodeViewSet, basename="api-sourcecodes")
router.register(r"share-options", ShareOptionViewSet, basename="api-shareoptions")
router.register(r"keys", APIKeyViewSet, basename="api-keys")

urlpatterns = router.urls
