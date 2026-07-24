import { Card, Spin, Empty, Typography, Row, Col } from 'antd';
import { useSummary, useCategories } from '@/hooks/useAnalysis';
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell,
  ResponsiveContainer,
} from 'recharts';
import type { PieLabelRenderProps } from 'recharts';

const { Title } = Typography;

const PLATFORM_COLORS: Record<string, string> = {
  wechat: '#52c41a',
  alipay: '#1677ff',
  bank: '#fa8c16',
};

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

const currencyFormatter = (value: number): string =>
  `¥${value.toFixed(2)}`;

const tooltipCurrencyFormatter = (
  value: number | string | ReadonlyArray<number | string> | undefined,
  _name: number | string | undefined,
): [string, string] => {
  const num = typeof value === 'number' ? value : 0;
  return [`¥${num.toFixed(2)}`, ''];
};

const categoryLabelFormatter = (props: PieLabelRenderProps): string => {
  const { name, percent, payload } = props;
  const nameStr = typeof name === 'string' ? name : '';
  const pctVal = typeof payload === 'object' && payload !== null && 'pct' in payload
    ? (payload as { pct: number }).pct
    : typeof percent === 'number'
      ? percent * 100
      : 0;
  return `${nameStr} ${pctVal.toFixed(1)}%`;
};

const categoryTooltipFormatter = (
  value: number | string | ReadonlyArray<number | string> | undefined,
): [string, string] => {
  const num = typeof value === 'number' ? value : 0;
  return [`¥${num.toFixed(2)}`, '金额'];
};

function PlatformCharts() {
  const {
    data: summaryData,
    isLoading: summaryLoading,
    isError: summaryError,
  } = useSummary();
  const {
    data: categories,
    isLoading: catLoading,
    isError: catError,
  } = useCategories();

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
    return <Empty description="无法加载图表数据" />;
  }

  const { monthly, summary } = summaryData;

  const platformData = [
    { name: '微信', amount: summary.wechat_total, color: PLATFORM_COLORS.wechat },
    { name: '支付宝', amount: summary.alipay_total, color: PLATFORM_COLORS.alipay },
    { name: '银行', amount: summary.boc_total, color: PLATFORM_COLORS.bank },
  ];

  return (
    <>
      <Title level={4} style={{ marginBottom: 16 }}>
        数据可视化
      </Title>

      <Row gutter={[16, 16]}>
        {/* Monthly Trend Line Chart */}
        <Col xs={24} xl={14}>
          <Card title="月度支出趋势">
            <ResponsiveContainer width="100%" height={360}>
              <LineChart data={monthly}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis tickFormatter={currencyFormatter} />
                <Tooltip formatter={tooltipCurrencyFormatter} />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="wechat"
                  name="微信"
                  stroke={PLATFORM_COLORS.wechat}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                />
                <Line
                  type="monotone"
                  dataKey="alipay"
                  name="支付宝"
                  stroke={PLATFORM_COLORS.alipay}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                />
                <Line
                  type="monotone"
                  dataKey="boc"
                  name="银行"
                  stroke={PLATFORM_COLORS.bank}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>

        {/* Category Pie Chart */}
        <Col xs={24} xl={10}>
          <Card title="消费类别分布">
            {categories && categories.length > 0 ? (
              <ResponsiveContainer width="100%" height={360}>
                <PieChart>
                  <Pie
                    data={categories}
                    dataKey="amount"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={120}
                    innerRadius={50}
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
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <Empty description="暂无类别数据" />
            )}
          </Card>
        </Col>

        {/* Platform Comparison Bar Chart */}
        <Col xs={24}>
          <Card title="平台消费对比">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={platformData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis tickFormatter={currencyFormatter} />
                <Tooltip formatter={tooltipCurrencyFormatter} />
                <Bar dataKey="amount" name="消费金额" radius={[6, 6, 0, 0]}>
                  {platformData.map((entry, index) => (
                    <Cell key={index} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>
    </>
  );
}

export default PlatformCharts;
