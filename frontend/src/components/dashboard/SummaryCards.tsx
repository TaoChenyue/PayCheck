import { Card, Statistic, Row, Col, Skeleton, Empty } from 'antd';
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  CalendarOutlined,
  OrderedListOutlined,
} from '@ant-design/icons';
import { useSummary } from '@/hooks/useAnalysis';

interface CardConfig {
  title: string;
  value: number;
  icon: React.ReactNode;
  color: string;
  bgColor: string;
  isCurrency: boolean;
}

function SummaryCards() {
  const { data, isLoading, isError } = useSummary();

  if (isLoading) {
    return (
      <Row gutter={[16, 16]}>
        {[1, 2, 3, 4].map((i) => (
          <Col xs={24} sm={12} lg={6} key={i}>
            <Card>
              <Skeleton active paragraph={{ rows: 1 }} />
            </Card>
          </Col>
        ))}
      </Row>
    );
  }

  if (isError || !data) {
    return <Empty description="无法加载摘要数据" />;
  }

  const { summary } = data;

  const cards: CardConfig[] = [
    {
      title: '总支出',
      value: summary.total_expense,
      icon: <ArrowUpOutlined />,
      color: '#cf1322',
      bgColor: '#fff2f0',
      isCurrency: true,
    },
    {
      title: '总收入',
      value: summary.total_income,
      icon: <ArrowDownOutlined />,
      color: '#3f8600',
      bgColor: '#f6ffed',
      isCurrency: true,
    },
    {
      title: '月均支出',
      value: summary.monthly_avg,
      icon: <CalendarOutlined />,
      color: '#1677ff',
      bgColor: '#e6f4ff',
      isCurrency: true,
    },
    {
      title: '交易笔数',
      value: summary.total_count,
      icon: <OrderedListOutlined />,
      color: '#fa8c16',
      bgColor: '#fff7e6',
      isCurrency: false,
    },
  ];

  return (
    <Row gutter={[16, 16]}>
      {cards.map((card) => (
        <Col xs={24} sm={12} lg={6} key={card.title}>
          <Card>
            <Statistic
              title={card.title}
              value={card.value}
              precision={card.isCurrency ? 2 : 0}
              prefix={
                card.isCurrency ? (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        width: 28,
                        height: 28,
                        borderRadius: 8,
                        background: card.bgColor,
                        color: card.color,
                        fontSize: 14,
                      }}
                    >
                      {card.icon}
                    </span>
                    ¥
                  </span>
                ) : (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: 28,
                      height: 28,
                      borderRadius: 8,
                      background: card.bgColor,
                      color: card.color,
                      fontSize: 14,
                      marginRight: 4,
                    }}
                  >
                    {card.icon}
                  </span>
                )
              }
              valueStyle={{ color: card.color }}
            />
          </Card>
        </Col>
      ))}
    </Row>
  );
}

export default SummaryCards;
