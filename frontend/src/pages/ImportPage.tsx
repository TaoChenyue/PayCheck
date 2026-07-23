import { useState } from 'react';
import { Typography, Divider, Card, List, Tag, Space } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import FileUploader from '@/components/import/FileUploader';
import ImportProgress from '@/components/import/ImportProgress';
import { useImportJobs } from '@/hooks/useImport';
import type { ImportUploadResponse, ImportJob, JobStatus } from '@/types';

const { Title, Text } = Typography;

// ── Constants ──

const JOB_STATUS_CONFIG: Record<JobStatus, { color: string; icon: React.ReactNode; label: string }> = {
  pending: { color: 'default', icon: <ClockCircleOutlined />, label: '等待中' },
  processing: { color: 'processing', icon: <SyncOutlined spin />, label: '处理中' },
  completed: { color: 'success', icon: <CheckCircleOutlined />, label: '已完成' },
  failed: { color: 'error', icon: <CloseCircleOutlined />, label: '失败' },
};

// ── Component ──

export default function ImportPage() {
  const [currentJobId, setCurrentJobId] = useState<number | null>(null);

  const { data: jobsData, isLoading: jobsLoading } = useImportJobs();

  const handleUploadSuccess = (response: ImportUploadResponse) => {
    setCurrentJobId(response.job_id);
  };

  return (
    <div style={{ padding: '0 24px', maxWidth: 960, margin: '0 auto' }}>
      {/* Page Title */}
      <Title level={3} style={{ marginBottom: 24 }}>数据导入</Title>

      {/* Upload Section */}
      <Card style={{ marginBottom: 24 }}>
        <FileUploader onUploadSuccess={handleUploadSuccess} />
      </Card>

      {/* Import Progress */}
      {currentJobId && (
        <div style={{ marginBottom: 24 }}>
          <ImportProgress jobId={currentJobId} />
        </div>
      )}

      {/* Recent Import Jobs History */}
      <Divider />

      <Card
        title={<Text strong>最近导入记录</Text>}
        loading={jobsLoading}
      >
        {jobsData && jobsData.results.length > 0 ? (
          <List
            size="small"
            dataSource={jobsData.results}
            renderItem={(job: ImportJob) => {
              const config = JOB_STATUS_CONFIG[job.status];
              return (
                <List.Item
                  extra={
                    <Tag color={config.color} icon={config.icon}>
                      {config.label}
                    </Tag>
                  }
                >
                  <List.Item.Meta
                    title={
                      <Text
                        style={{ cursor: 'pointer' }}
                        onClick={() => setCurrentJobId(job.id)}
                      >
                        任务 #{job.id}
                        {job.id === currentJobId && (
                          <Text type="secondary" style={{ marginLeft: 8 }}>(当前查看)</Text>
                        )}
                      </Text>
                    }
                    description={
                      <Space size="middle">
                        <Text type="secondary">
                          {job.processed} / {job.total_files} 个文件
                        </Text>
                        {job.completed_at && (
                          <Text type="secondary">
                            完成于 {new Date(job.completed_at).toLocaleString('zh-CN')}
                          </Text>
                        )}
                      </Space>
                    }
                  />
                </List.Item>
              );
            }}
            style={{ maxHeight: 300, overflow: 'auto' }}
          />
        ) : (
          <Text type="secondary">暂无导入记录</Text>
        )}
      </Card>
    </div>
  );
}
