import { Card, Table, Spin, Empty, Typography, Row, Col } from 'antd';
import { useSummary, useCategories } from '@/hooks/useAnalysis';
import SummaryCards from '@/components/dashboard/SummaryCards';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { PieLabelRenderProps } from 'recharts';
import type { CategoryData } from '@/types';

const { Title } = Typography;

const CATEGORY_COLORS = [
  '#1677ff',
  '#52c41a',
  '#fa8c16',
  '#722ed1',
  '#eb2f96',
  '#13c2c2',
  '#fadb14',
  '#fa541c',
  '#2f54eb',
  '#a0d911',
];

const categoryLabelFormatter = (props: PieLabelRenderProps): string => {
  const { name, percent } = props;
  const nameStr = typeof name === 'string' ? name : '';
  const pctVal = typeof percent === 'number' ? percent * 100 : 0;
  return `${nameStr} ${pctVal.toFixed(1)}%`;
};

const categoryTooltipFormatter = (
  value: number | string | ReadonlyArray<number | string> | undefined,
): [string, string] => {
  const num = typeof value === 'number' ? value : 0;
  return [`¥${num.toFixed(2)}`, '金额'];
};

const rankingColumns = [
  {
    title: '排名',
    key: 'rank',
    width: 60,
    render: (_: unknown, __: unknown, index: number) => index + 1,
  },
  {
    title: '类别',
    dataIndex: 'name',
    key: 'name',
  },
  {
    title: '金额',
    dataIndex: 'amount',
    key: 'amount',
    render: (value: number) => `¥${value.toFixed(2)}`,
    sorter: (a: CategoryData, b: CategoryData) => a.amount - b.amount,
    defaultSortOrder: 'descend' as const,
  },
  {
    title: '占比',
    dataIndex: 'pct',
    key: 'pct',
    render: (value: number) => `${value.toFixed(1)}%`,
    sorter: (a: CategoryData, b: CategoryData) => a.pct - b.pct,
  },
  {
    title: '笔数',
    dataIndex: 'count',
    key: 'count',
    sorter: (a: CategoryData, b: CategoryData) => a.count - b.count,
  },
];

function AnalysisPage() {
  const {
    data: summaryData,
    isLoading: summaryLoading,
    isError: summaryError,
  } = useSummary();
  const {
    data: categories,
    isLoading: catLoading,
    isError: catError,
  } = useCategories(50);

  const isLoading = summaryLoading || catLoading;
  const isError = summaryError || catError;

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (isError || !summaryData) {
    return <Empty description="无法加载分析数据" />;
  }

  return (
    <div style={{ padding: 24 }}>
      <Title level={2} style={{ marginBottom: 24 }}>
        详细分析
      </Title>

      <SummaryCards />

      <Row gutter={[24, 24]} style={{ marginTop: 32 }}>
        {/* Category Pie Chart */}
        <Col xs={24} lg={14}>
          <Card title="消费类别分布">
            {categories && categories.length > 0 ? (
              <ResponsiveContainer width="100%" height={420}>
                <PieChart>
                  <Pie
                    data={categories}
                    dataKey="amount"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={150}
                    innerRadius={60}
                    label={categoryLabelFormatter}
                    labelLine={{ strokeWidth: 1 }}
                  >
                    {categories.map((_, index) => (
                      <Cell
                        key={index}
                        fill={CATEGORY_COLORS[index % CATEGORY_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip formatter={categoryTooltipFormatter} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <Empty description="暂无类别数据" />
            )}
          </Card>
        </Col>

        {/* Category Ranking Table */}
        <Col xs={24} lg={10}>
          <Card title="类别排名" bodyStyle={{ padding: 0 }}>
            {categories && categories.length > 0 ? (
              <Table
                dataSource={categories}
                columns={rankingColumns}
                rowKey="name"
                size="small"
                pagination={false}
                scroll={{ y: 420 }}
              />
            ) : (
              <Empty description="暂无类别数据" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}

export default AnalysisPage;
