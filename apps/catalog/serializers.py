from rest_framework import serializers


class CatalogSearchResultSerializer(serializers.Serializer):
    gutenberg_id = serializers.IntegerField()
    title = serializers.CharField()
    author = serializers.CharField()
    language = serializers.CharField()
    subjects = serializers.ListField(child=serializers.CharField())
    cover_url = serializers.CharField()
    in_library = serializers.BooleanField(default=False)
    catalog_status = serializers.CharField(default=None, allow_null=True)


class CatalogImportSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=['gutenberg'])
    external_id = serializers.CharField(max_length=100)
    title = serializers.CharField(max_length=500)
    author = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')
