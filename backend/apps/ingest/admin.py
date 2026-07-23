"""数据导入 Django Admin 配置"""

from django.contrib import admin

from apps.ingest.models import ImportJob, ImportFile


class ImportFileInline(admin.TabularInline):
    """导入文件内联显示"""

    model = ImportFile
    extra = 0
    readonly_fields = ["id", "filename", "file_type", "status", "error_msg", "created_at"]
    fields = ["id", "filename", "file_type", "status", "error_msg", "created_at"]


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    """导入任务 Admin"""

    list_display = [
        "id", "status", "total_files", "processed", "created_at", "completed_at",
    ]
    list_filter = ["status"]
    inlines = [ImportFileInline]
    list_per_page = 30


@admin.register(ImportFile)
class ImportFileAdmin(admin.ModelAdmin):
    """导入文件 Admin"""

    list_display = [
        "id", "job_id", "filename", "file_type", "status", "created_at",
    ]
    list_filter = ["file_type", "status"]
    search_fields = ["filename"]
    list_per_page = 50
