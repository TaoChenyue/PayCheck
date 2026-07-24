import { useState, useCallback } from 'react';
import { Upload, Button, Select, Space, Typography, Alert, List } from 'antd';
import type { UploadProps, UploadFile } from 'antd';
import { InboxOutlined, DeleteOutlined } from '@ant-design/icons';
import { useUploadFiles } from '@/hooks/useImport';
import type { ChannelType, ImportUploadResponse } from '@/types';

const { Dragger } = Upload;
const { Text } = Typography;

// ── Constants ──

const CHANNEL_OPTIONS: { value: ChannelType; label: string }[] = [
  { value: 'alipay', label: '支付宝' },
  { value: 'wechat', label: '微信' },
  { value: 'bank', label: '中国银行' },
];

const CHANNEL_ACCEPT: Record<ChannelType, string> = {
  alipay: '.csv',
  wechat: '.xlsx,.xls',
  bank: '.pdf,.csv',
};

const CHANNEL_HINTS: Record<ChannelType, string> = {
  alipay: '支持 .csv 格式的支付宝账单文件',
  wechat: '支持 .xlsx / .xls 格式的微信账单文件',
  bank: '支持 .pdf / .csv 格式的中国银行流水文件',
};

// ── Props ──

interface FileUploaderProps {
  onUploadSuccess?: (response: ImportUploadResponse) => void;
}

// ── Component ──

export default function FileUploader(_props: FileUploaderProps) {
  const [channel, setChannel] = useState<ChannelType>('alipay');
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const uploadMutation = useUploadFiles();

  const handleChannelChange = useCallback((value: ChannelType) => {
    setChannel(value);
    setFileList([]);
  }, []);

  const handleUploadChange: UploadProps['onChange'] = useCallback((info) => {
    setFileList(info.fileList);
  }, []);

  const handleRemove = useCallback((file: UploadFile) => {
    setFileList((prev) => prev.filter((f) => f.uid !== file.uid));
  }, []);

  const handleSubmit = useCallback(() => {
    const files: File[] = fileList
      .map((f) => f.originFileObj)
      .filter((f): f is NonNullable<typeof f> => f != null);

    if (files.length === 0) return;

    uploadMutation.mutate({ channel, files });
  }, [channel, fileList, uploadMutation]);

  const beforeUpload: UploadProps['beforeUpload'] = useCallback(() => false, []);

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {/* Channel Selector */}
      <Space align="center" size="small">
        <Text strong>导入渠道：</Text>
        <Select
          value={channel}
          onChange={handleChannelChange}
          options={CHANNEL_OPTIONS}
          style={{ width: 140 }}
        />
        <Text type="secondary">{CHANNEL_HINTS[channel]}</Text>
      </Space>

      {/* Drag & Drop Upload */}
      <Dragger
        multiple
        accept={CHANNEL_ACCEPT[channel]}
        fileList={fileList}
        onChange={handleUploadChange}
        beforeUpload={beforeUpload}
        showUploadList={false}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
        <p className="ant-upload-hint">
          {CHANNEL_HINTS[channel]}
        </p>
      </Dragger>

      {/* Selected Files List */}
      {fileList.length > 0 && (
        <List
          size="small"
          header={<Text strong>已选择的文件 ({fileList.length})</Text>}
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
                />,
              ]}
            >
              <Text>{file.name}</Text>
            </List.Item>
          )}
          style={{ maxHeight: 200, overflow: 'auto' }}
        />
      )}

      {/* Submit Button */}
      <Button
        type="primary"
        onClick={handleSubmit}
        loading={uploadMutation.isPending}
        disabled={fileList.length === 0}
        block
      >
        开始导入
      </Button>

      {/* Upload Result */}
      {uploadMutation.isSuccess && uploadMutation.data && (
        <Alert
          type="success"
          showIcon
          message="上传成功"
          description={
            <Space direction="vertical" size="small">
              <Text>
                导入任务已创建，任务 ID：<Text code>{uploadMutation.data.job_id}</Text>
              </Text>
              <Text>共 {uploadMutation.data.total_files} 个文件，状态：{uploadMutation.data.status}</Text>
            </Space>
          }
        />
      )}

      {uploadMutation.isError && (
        <Alert
          type="error"
          showIcon
          message="上传失败"
          description={
            uploadMutation.error instanceof Error
              ? uploadMutation.error.message
              : '未知错误，请重试'
          }
        />
      )}
    </Space>
  );
}
