import { Empty, Button, Typography, Space } from 'antd';
import { useNavigate } from 'react-router-dom';
import { ImportOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface EmptyStateProps {
  /** Custom description text */
  description?: string;
  /** Show "导入数据" action button linking to /import */
  showImportAction?: boolean;
}

/** 空数据引导提示 — 无数据时展示，引导用户导入数据 */
export default function EmptyState({
  description = '暂无交易数据，请先导入账单文件。',
  showImportAction = true,
}: EmptyStateProps) {
  const navigate = useNavigate();

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 320,
        padding: 48,
      }}
    >
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <Space direction="vertical" size={8}>
            <Text type="secondary">{description}</Text>
          </Space>
        }
      >
        {showImportAction && (
          <Button
            type="primary"
            icon={<ImportOutlined />}
            onClick={() => navigate('/import')}
          >
            导入数据
          </Button>
        )}
      </Empty>
    </div>
  );
}
