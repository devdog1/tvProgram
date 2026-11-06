from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from .models import (
    Program,
    Series,
    Category,
    Community,
    SourceCode,
    ShareOption,
    ProgramAttachment,
    CustomField,
    CustomFieldValue,
    APIKey,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "display_name", "is_enabled", "created_at"]


class CommunitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Community
        fields = ["id", "name", "is_enabled", "created_at"]


class SourceCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceCode
        fields = ["id", "name", "is_enabled", "created_at"]


class ShareOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShareOption
        fields = ["id", "name", "is_enabled", "created_at"]


class ProgramAttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ProgramAttachment
        fields = ["id", "program", "filename", "file_size", "uploaded_at", "download_url"]

    @extend_schema_field(OpenApiTypes.URI)
    def get_download_url(self, obj) -> str:
        if obj.file:
            return obj.file.url
        return None


class SeriesSerializer(serializers.ModelSerializer):
    episodes_count = serializers.IntegerField(source="episodes.count", read_only=True)
    owner_group_name = serializers.CharField(source="owner_group.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Series
        fields = [
            "id",
            "title",
            "description",
            "series_type",
            "status",
            "owner_group",
            "owner_group_name",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
            "episodes_count",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]


class ProgramSerializer(serializers.ModelSerializer):
    owner_group_name = serializers.CharField(source="owner_group.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    signed_off_by_username = serializers.CharField(source="signed_off_by.username", read_only=True)
    series_title = serializers.CharField(source="series.title", read_only=True)
    attachments = ProgramAttachmentSerializer(many=True, read_only=True)
    custom_fields = serializers.SerializerMethodField()

    class Meta:
        model = Program
        fields = [
            "id",
            "title",
            "date_recorded",
            "expiry_date",
            "producer",
            "length",
            "category",
            "community",
            "source_code",
            "share",
            "filename",
            "comments",
            "series",
            "series_title",
            "season_number",
            "episode_number",
            "part_number",
            "status",
            "owner_group",
            "owner_group_name",
            "created_by",
            "created_by_username",
            "signed_off_by",
            "signed_off_by_username",
            "signed_off_at",
            "created",
            "attachments",
            "custom_fields",
        ]
        read_only_fields = [
            "created_by",
            "signed_off_by",
            "signed_off_at",
            "created",
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_custom_fields(self, obj) -> dict:
        values = CustomFieldValue.objects.filter(program=obj).select_related("custom_field")
        res = {}
        for val in values:
            if val.custom_field.field_type == "file" and val.file_upload:
                res[val.custom_field.name] = val.file_upload.url
            else:
                res[val.custom_field.name] = val.value
        return res


class APIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ["id", "name", "prefix", "key", "is_active", "created_at", "last_used_at"]
        read_only_fields = ["prefix", "created_at", "last_used_at"]
        extra_kwargs = {
            "key": {"read_only": True},
        }
