import { Typography } from 'antd';
import SummaryCards from '@/components/dashboard/SummaryCards';
import PlatformCharts from '@/components/dashboard/PlatformCharts';

const { Title } = Typography;

function DashboardPage() {
  return (
    <div style={{ padding: 24 }}>
      <Title level={2} style={{ marginBottom: 24 }}>
        概览仪表盘
      </Title>
      <SummaryCards />
      <div style={{ marginTop: 32 }}>
        <PlatformCharts />
      </div>
    </div>
  );
}

export default DashboardPage;
