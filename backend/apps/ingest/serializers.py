"""导入任务序列化器"""

from rest_framework import serializers

from apps.ingest.models import ImportJob, ImportFile


class ImportFileSerializer(serializers.ModelSerializer):
    """导入文件序列化器"""

    class Meta:
        model = ImportFile
        fields = "__all__"


class ImportJobSerializer(serializers.ModelSerializer):
    """导入任务序列化器 — 含嵌套文件列表"""

    files = ImportFileSerializer(many=True, read_only=True)

    class Meta:
        model = ImportJob
        fields = "__all__"
