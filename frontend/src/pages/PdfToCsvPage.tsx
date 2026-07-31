import { useState, useCallback, useEffect } from 'react';
import {
  Upload,
  Button,
  Select,
  Card,
  Typography,
  Progress,
  List,
  Tag,
  Space,
  Divider,
  Alert,
  Spin,
  message,
} from 'antd';
import type { UploadProps, UploadFile } from 'antd';
import {
  FilePdfOutlined,
  FileTextOutlined,
  DownloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  InboxOutlined,
  LoadingOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useUploadFiles, useImportJob } from '@/hooks/useImport';
import type { ChannelType, ImportFile, JobStatus } from '@/types';

const { Dragger } = Upload;
const { Title, Text, Paragraph } = Typography;

// ── Constants ──

const BANK_OPTIONS: { value: ChannelType; label: string }[] = [
  { value: 'boc', label: '中国银行 (BOC)' },
];

const STATUS_CONFIG: Record<JobStatus, { color: string; icon: React.ReactNode; label: string }> = {
  pending: { color: 'default', icon: <FileTextOutlined />, label: '等待中' },
  processing: { color: 'processing', icon: <LoadingOutlined />, label: '转换中' },
  completed: { color: 'success', icon: <CheckCircleOutlined />, label: '已完成' },
  failed: { color: 'error', icon: <CloseCircleOutlined />, label: '失败' },
};

// ── Types ──

type PageStage = 'select' | 'uploading' | 'converting' | 'done';

// ── Helpers ──

// TODO: 后端缺少文件下载端点（ImportJobViewSet 仅有 list/retrieve，无 download action）。
// 需要后端在 apps/ingest/views.py 中添加文件下载视图并在 urls.py 注册后，前端再启用下载按钮。
// 参考端点格式：`/api/import/files/${fileId}/download/`

function getStatusTag(status: JobStatus) {
  const config = STATUS_CONFIG[status];
  return (
    <Tag color={config.color} icon={config.icon}>
      {config.label}
    </Tag>
  );
}

// ── Component ──

export default function PdfToCsvPage() {
  const [stage, setStage] = useState<PageStage>('select');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [bankType, setBankType] = useState<ChannelType>('boc');
  const [jobId, setJobId] = useState<number | null>(null);
  const [refetchInterval, setRefetchInterval] = useState<number | false>(false);

  const uploadMutation = useUploadFiles();

  const {
    data: job,
    isLoading: isJobLoading,
    isError: isJobError,
  } = useImportJob(jobId ?? 0, {
    enabled: jobId !== null,
    refetchInterval,
  });

  // ── Auto-stop polling on terminal state ──

  useEffect(() => {
    if (job && (job.status === 'completed' || job.status === 'failed')) {
      setRefetchInterval(false);
      setStage('done');
    }
  }, [job?.status]);

  // ── Handlers ──

  const handleBankChange = useCallback((value: ChannelType) => {
    setBankType(value);
    setFileList([]);
  }, []);

  const handleUploadChange: UploadProps['onChange'] = useCallback((info) => {
    setFileList(info.fileList);
  }, []);

  const handleRemove = useCallback((file: UploadFile) => {
    setFileList((prev) => prev.filter((f) => f.uid !== file.uid));
  }, []);

  const beforeUpload: UploadProps['beforeUpload'] = useCallback(() => false, []);

  const handleConvert = useCallback(async () => {
    const files = fileList.flatMap((f) => (f.originFileObj ? [f.originFileObj] : []));

    if (files.length === 0) {
      message.warning('请先选择 PDF 文件');
      return;
    }

    setStage('uploading');

    try {
      const response = await uploadMutation.mutateAsync({ channel: bankType, files });
      setJobId(response.job_id);
      setRefetchInterval(2000);
      setStage('converting');
      message.success(`上传成功，任务 ID：${response.job_id}，开始转换...`);
    } catch {
      setStage('select');
      // Error handled by uploadMutation.isError
    }
  }, [fileList, bankType, uploadMutation]);

  const handleReset = useCallback(() => {
    setStage('select');
    setFileList([]);
    setJobId(null);
    setRefetchInterval(false);
    uploadMutation.reset();
  }, [uploadMutation]);

  // ── Derived values for progress ──

  const percentComplete = job && job.total_files > 0
    ? Math.round((job.processed / job.total_files) * 100)
    : 0;

  const isSelectStage = stage === 'select' || stage === 'uploading';
  const isProcessingStage = stage === 'converting' || stage === 'done';

  // ── Render ──

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '32px 24px' }}>
      {/* Page Header */}
      <div style={{ marginBottom: 32, textAlign: 'center' }}>
        <Title level={2} style={{ marginBottom: 8 }}>
          <FilePdfOutlined style={{ marginRight: 12, color: 'var(--accent, #aa3bff)' }} />
          PDF 转 CSV 工具
        </Title>
        <Paragraph type="secondary" style={{ fontSize: 16, maxWidth: 560, margin: '0 auto' }}>
          将银行 PDF 流水文件转换为结构化的 CSV 格式。
          支持中国银行（BOC）PDF 流水，基于 OCR 识别技术自动提取交易数据。
        </Paragraph>
      </div>

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* ── Upload Section ── */}
        {isSelectStage && (
          <Card
            title={
              <Space>
                <FilePdfOutlined />
                <Text strong>上传 PDF 文件</Text>
              </Space>
            }
          >
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              {/* Bank type selector */}
              <Space align="center" size="small">
                <Text strong>银行类型：</Text>
                <Select
                  value={bankType}
                  onChange={handleBankChange}
                  options={BANK_OPTIONS}
                  style={{ width: 200 }}
                  disabled={stage === 'uploading'}
                />
              </Space>

              {/* Drag & Drop Upload */}
              <Dragger
                multiple
                accept=".pdf"
                fileList={fileList}
                onChange={handleUploadChange}
                beforeUpload={beforeUpload}
                showUploadList={false}
                disabled={stage === 'uploading'}
              >
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p className="ant-upload-text">点击或拖拽 PDF 文件到此区域</p>
                <p className="ant-upload-hint">
                  支持批量上传，仅接受 .pdf 格式的银行流水文件
                </p>
              </Dragger>

              {/* Selected Files List */}
              {fileList.length > 0 && (
                <List
                  size="small"
                  header={
                    <Text strong>
                      已选择的文件（{fileList.length} 个）
                    </Text>
                  }
                  dataSource={fileList}
                  renderItem={(file) => (
                    <List.Item
                      actions={[
                        <Button
                          key="remove"
                          type="text"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                          onClick={() => handleRemove(file)}
                          disabled={stage === 'uploading'}
                        />,
                      ]}
                    >
                      <Space>
                        <FilePdfOutlined style={{ color: '#ff4d4f' }} />
                        <Text>{file.name}</Text>
                      </Space>
                    </List.Item>
                  )}
                  style={{ maxHeight: 240, overflow: 'auto' }}
                />
              )}

              {/* Submit Button */}
              <Button
                type="primary"
                size="large"
                onClick={handleConvert}
                loading={stage === 'uploading'}
                disabled={fileList.length === 0 || stage === 'uploading'}
                block
                icon={<FileTextOutlined />}
              >
                {stage === 'uploading' ? '正在上传...' : '开始转换'}
              </Button>
            </Space>
          </Card>
        )}

        {/* ── Upload Error ── */}
        {uploadMutation.isError && (
          <Alert
            type="error"
            showIcon
            closable
            message="上传失败"
            description={
              uploadMutation.error instanceof Error
                ? uploadMutation.error.message
                : '未知错误，请重试'
            }
            action={
              <Button size="small" onClick={handleReset}>
                重试
              </Button>
            }
          />
        )}

        {/* ── Progress / Results Section ── */}
        {isProcessingStage && (
          <Card
            title={
              <Space>
                {job ? (
                  <>
                    <Text strong>
                      {job.status === 'completed' ? '转换完成' : '转换进度'}
                    </Text>
                    <Tag
                      color={
                        job.status === 'completed'
                          ? 'success'
                          : job.status === 'failed'
                            ? 'error'
                            : 'processing'
                      }
                    >
                      任务 #{job.id}
                    </Tag>
                  </>
                ) : (
                  <Text strong>转换进度</Text>
                )}
              </Space>
            }
            extra={
              job && job.status === 'completed' && (
                <Button
                  icon={<ReloadOutlined />}
                  onClick={handleReset}
                >
                  重新转换
                </Button>
              )
            }
          >
            {/* Loading state */}
            {isJobLoading && !job && (
              <div style={{ textAlign: 'center', padding: '40px 0' }}>
                <Spin
                  indicator={<LoadingOutlined style={{ fontSize: 36 }} spin />}
                  tip="正在加载转换进度..."
                />
              </div>
            )}

            {/* Error state */}
            {isJobError && !job && (
              <Alert
                type="error"
                showIcon
                message="加载进度失败"
                description="无法获取转换进度，请刷新页面或重试。"
                action={
                  <Button size="small" onClick={handleReset}>
                    重试
                  </Button>
                }
              />
            )}

            {/* Job data available */}
            {job && (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                {/* Overall Progress */}
                <div>
                  <Progress
                    percent={percentComplete}
                    status={
                      job.status === 'failed'
                        ? 'exception'
                        : job.status === 'completed'
                          ? 'success'
                          : 'active'
                    }
                    format={() => `${job.processed} / ${job.total_files}`}
                  />
                  <Text type="secondary">
                    已处理 {job.processed} 个文件，共 {job.total_files} 个文件
                    {job.completed_at && (
                      <>
                        ，完成于{' '}
                        {new Date(job.completed_at).toLocaleString('zh-CN')}
                      </>
                    )}
                  </Text>
                </div>

                <Divider style={{ margin: '8px 0' }} />

                {/* File-level Status List */}
                {job.files.length > 0 ? (
                  <List
                    size="small"
                    header={<Text strong>文件详情</Text>}
                    dataSource={job.files}
                    renderItem={(file: ImportFile) => (
                      <List.Item
                        extra={
                          <Space>
                            {getStatusTag(file.status)}
                            {file.status === 'completed' && (
                              <Button
                                type="link"
                                size="small"
                                icon={<DownloadOutlined />}
                                disabled
                                title="后端下载端点暂未实现"
                              >
                                下载 CSV
                              </Button>
                            )}
                          </Space>
                        }
                      >
                        <List.Item.Meta
                          title={
                            <Space>
                              <FilePdfOutlined
                                style={{
                                  color:
                                    file.status === 'failed'
                                      ? '#ff4d4f'
                                      : file.status === 'completed'
                                        ? '#52c41a'
                                        : 'var(--accent, #aa3bff)',
                                }}
                              />
                              <Text
                                delete={file.status === 'failed'}
                              >
                                {file.filename}
                              </Text>
                            </Space>
                          }
                          description={
                            file.status === 'failed' && file.error_msg ? (
                              <Text type="danger">{file.error_msg}</Text>
                            ) : undefined
                          }
                        />
                      </List.Item>
                    )}
                    style={{ maxHeight: 360, overflow: 'auto' }}
                  />
                ) : (
                  <div style={{ textAlign: 'center', padding: '24px 0' }}>
                    <Text type="secondary">暂无文件信息</Text>
                  </div>
                )}
              </Space>
            )}
          </Card>
        )}

        {/* ── Empty state hint (when no files and no job) ── */}
        {isSelectStage && fileList.length === 0 && !jobId && (
          <Card>
            <div style={{ textAlign: 'center', padding: '16px 0' }}>
              <FilePdfOutlined
                style={{ fontSize: 48, color: 'var(--accent, #aa3bff)', opacity: 0.3, marginBottom: 16 }}
              />
              <Paragraph type="secondary">
                请选择银行类型并上传 PDF 流水文件，然后点击「开始转换」按钮。
              </Paragraph>
              <Paragraph type="secondary">
                转换过程可能需要几分钟时间，请耐心等待。
              </Paragraph>
            </div>
          </Card>
        )}
      </Space>
    </div>
  );
}
