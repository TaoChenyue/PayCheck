"""导入任务管理模型"""

from django.db import models


class ImportJob(models.Model):
    """导入任务 — 追踪批量导入的整体状态"""

    STATUS_CHOICES = [
        ("pending", "待处理"),
        ("processing", "处理中"),
        ("completed", "已完成"),
        ("failed", "失败"),
    ]

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending"
    )
    total_files = models.IntegerField(default=0)
    processed = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "import_jobs"

    def __str__(self):
        return f"Job#{self.id} ({self.status})"


class ImportFile(models.Model):
    """导入文件 — 追踪单个文件的解析状态"""

    FILE_TYPE_CHOICES = [
        ("alipay_csv", "支付宝CSV"),
        ("wechat_xlsx", "微信XLSX"),
        ("boc_pdf", "银行PDF"),
        ("boc_csv", "银行CSV"),
    ]

    STATUS_CHOICES = [
        ("pending", "待处理"),
        ("processing", "处理中"),
        ("completed", "已完成"),
        ("failed", "失败"),
    ]

    job = models.ForeignKey(
        ImportJob, on_delete=models.CASCADE, related_name="files"
    )
    filename = models.CharField(max_length=500)
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending"
    )
    error_msg = models.TextField(default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "import_files"

    def __str__(self):
        return f"{self.filename} ({self.status})"
