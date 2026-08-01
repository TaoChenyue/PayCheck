"""导入上传与任务管理 ViewSet"""

import os

from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.ingest.models import ImportJob, ImportFile
from apps.ingest.serializers import ImportJobSerializer
from apps.ingest.tasks import process_import_job
from apps.ingest.executor import get_executor


class ImportUploadView(APIView):
    """文件上传接口

    POST /api/import/upload/
    请求：multipart/form-data
      - channel: "alipay" | "wechat" | "boc" (必选)
      - files: 多文件上传 (最多 20 个)
    响应：job_id, status, total_files, files 列表
    """

    def post(self, request):
        channel = request.data.get("channel")
        if channel not in ("alipay", "wechat", "boc"):
            return Response(
                {"error": "channel must be alipay, wechat, or boc"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uploaded_files = request.FILES.getlist("files")
        if not uploaded_files:
            return Response(
                {"error": "No files provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(uploaded_files) > 20:
            return Response(
                {"error": "Maximum 20 files allowed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 文件类型推断
        file_type_map = {
            "alipay": "alipay_csv",
            "wechat": "wechat_xlsx",
            "boc_pdf": "boc_pdf",
            "boc_csv": "boc_csv",
        }

        # 创建 ImportJob
        job = ImportJob.objects.create(
            status="pending",
            total_files=len(uploaded_files),
            processed=0,
        )

        # 创建上传目录
        upload_dir = os.path.join(settings.MEDIA_ROOT, "uploads", str(job.id))
        os.makedirs(upload_dir, exist_ok=True)

        import_files = []
        for f in uploaded_files:
            # 推断文件类型
            ext = os.path.splitext(f.name)[1].lower()
            if channel == "alipay" and ext == ".csv":
                file_type = "alipay_csv"
            elif channel == "wechat" and ext in (".xlsx", ".xls"):
                file_type = "wechat_xlsx"
            elif channel == "boc":
                if ext == ".pdf":
                    file_type = "boc_pdf"
                elif ext == ".csv":
                    file_type = "boc_csv"
                else:
                    file_type = "boc_csv"
            else:
                file_type = f"{channel}_csv"

            # 保存文件
            save_path = os.path.join(upload_dir, f.name)
            with open(save_path, "wb") as dest:
                for chunk in f.chunks():
                    dest.write(chunk)

            import_file = ImportFile.objects.create(
                job=job,
                filename=save_path,
                file_type=file_type,
                status="pending",
            )
            import_files.append(import_file)

        # 启动异步处理
        get_executor().submit(process_import_job, job.id)

        return Response(
            {
                "job_id": job.id,
                "status": job.status,
                "total_files": job.total_files,
                "files": [
                    {
                        "id": f.id,
                        "filename": os.path.basename(f.filename),
                        "status": f.status,
                    }
                    for f in import_files
                ],
            },
            status=status.HTTP_201_CREATED,
        )


class ImportJobViewSet(ReadOnlyModelViewSet):
    """导入任务查询接口 — 只读，查看任务状态和进度"""

    queryset = ImportJob.objects.prefetch_related("files").all()
    serializer_class = ImportJobSerializer


class ImportFileDownloadView(APIView):
    """文件下载接口

    GET /api/import/files/{id}/download/
    返回 CSV 文件。对于 boc_pdf 类型，返回 OCR 生成的 CSV 文件；
    对于其他类型，返回原始上传文件。
    """

    def get(self, request, file_id):
        try:
            import_file = ImportFile.objects.get(id=file_id)
        except ImportFile.DoesNotExist:
            raise Http404("Import file not found")

        file_path = import_file.filename

        # For BOC PDF files, return the OCR-generated CSV
        if import_file.file_type == "boc_pdf":
            output_dir = os.path.dirname(file_path)
            csv_path = os.path.join(
                output_dir,
                f"{os.path.splitext(os.path.basename(file_path))[0]}.csv",
            )
            if os.path.exists(csv_path):
                file_path = csv_path
            else:
                raise Http404("Converted CSV file not found")

        if not os.path.exists(file_path):
            raise Http404("File not found on disk")

        filename = os.path.basename(file_path)
        response = FileResponse(open(file_path, "rb"), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )
        return response
