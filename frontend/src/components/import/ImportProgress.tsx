import { useState, useEffect } from 'react';
import { Progress, Badge, List, Typography, Card, Spin, Space } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { useImportJob } from '@/hooks/useImport';
import type { JobStatus, FileType, ImportFile } from '@/types';

const { Text } = Typography;

// ── Constants ──

const STATUS_CONFIG: Record<JobStatus, { color: string; icon: React.ReactNode; label: string }> = {
  pending: { color: 'default', icon: <ClockCircleOutlined />, label: '等待中' },
  processing: { color: 'processing', icon: <LoadingOutlined />, label: '处理中' },
  completed: { color: 'success', icon: <CheckCircleOutlined />, label: '已完成' },
  failed: { color: 'error', icon: <CloseCircleOutlined />, label: '失败' },
};

const FILE_TYPE_LABELS: Record<FileType, string> = {
  alipay_csv: '支付宝CSV',
  wechat_xlsx: '微信Excel',
  boc_pdf: '银行PDF',
  boc_csv: '银行CSV',
};

// ── Props ──

interface ImportProgressProps {
  jobId: number;
}

// ── Helpers ──

function getFileStatusBadge(file: ImportFile) {
  const config = STATUS_CONFIG[file.status];
  return (
    <Badge
      status={config.color as 'default' | 'processing' | 'success' | 'error'}
      text={config.label}
    />
  );
}

// ── Component ──

export default function ImportProgress({ jobId }: ImportProgressProps) {
  const [refetchInterval, setRefetchInterval] = useState<number | false>(2000);

  const {
    data: job,
    isLoading,
    isError,
  } = useImportJob(jobId, {
    enabled: !!jobId,
    refetchInterval,
  });

  // Auto-stop polling when job reaches terminal state
  useEffect(() => {
    if (job && (job.status === 'completed' || job.status === 'failed')) {
      setRefetchInterval(false);
    }
  }, [job?.status]);

  // ── Loading state ──

  if (isLoading) {
    return (
      <Card>
        <Spin tip="正在加载导入进度..." style={{ display: 'block', textAlign: 'center' }}>
          <div style={{ height: 100 }} />
        </Spin>
      </Card>
    );
  }

  // ── Error state ──

  if (isError || !job) {
    return (
      <Card>
        <Text type="danger">加载导入进度失败，请刷新页面重试。</Text>
      </Card>
    );
  }

  // ── Job status config ──

  const jobConfig = STATUS_CONFIG[job.status];
  const percentComplete = job.total_files > 0
    ? Math.round((job.processed / job.total_files) * 100)
    : 0;

  // ── Render ──

  return (
    <Card
      title={
        <Space>
          <Text strong>导入进度</Text>
          <Badge
            status={jobConfig.color as 'default' | 'processing' | 'success' | 'error'}
            text={`任务 #${job.id} — ${jobConfig.label}`}
          />
        </Space>
      }
    >
      {/* Overall Progress */}
      <div style={{ marginBottom: 24 }}>
        <Progress
          percent={percentComplete}
          status={job.status === 'failed' ? 'exception' : job.status === 'completed' ? 'success' : 'active'}
          format={() => `${job.processed} / ${job.total_files}`}
        />
        <Text type="secondary">
          已处理 {job.processed} 个文件，共 {job.total_files} 个文件
        </Text>
      </div>

      {/* File-level Status List */}
      <List
        size="small"
        header={<Text strong>文件详情</Text>}
        dataSource={job.files}
        renderItem={(file) => (
          <List.Item
            extra={getFileStatusBadge(file)}
          >
            <List.Item.Meta
              title={
                <Space>
                  <Text>{file.filename}</Text>
                  <Text type="secondary">
                    ({FILE_TYPE_LABELS[file.file_type] ?? file.file_type})
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
        style={{ maxHeight: 320, overflow: 'auto' }}
      />
    </Card>
  );
}
