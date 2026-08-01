import { useState, useMemo, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  Typography,
  Select,
  DatePicker,
  InputNumber,
  Input,
  Space,
  Row,
  Col,
  Collapse,
  Button,
} from 'antd';
import { FilterOutlined, ClearOutlined } from '@ant-design/icons';
import { useTransactions } from '@/hooks/useTransactions';
import { useTags } from '@/hooks/useTags';
import ChannelTable from '@/components/tables/ChannelTable';
import EmptyState from '@/components/common/EmptyState';
import type { TransactionQueryParams, ChannelType } from '@/types';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

// ── channel metadata ──

const CHANNEL_LABELS: Record<string, string> = {
  alipay: '支付宝账单',
  wechat: '微信账单',
  boc: '中国银行账单',
};

const CHANNEL_PLATFORM: Record<string, ChannelType> = {
  alipay: 'alipay',
  wechat: 'wechat',
  boc: 'boc',
};

const VALID_CHANNELS = ['alipay', 'wechat', 'boc'] as const;

const TX_TYPE_OPTIONS = [
  { label: '全部', value: '' },
  { label: '支出', value: 'expense' },
  { label: '收入', value: 'income' },
  { label: '转账', value: 'transfer' },
  { label: '其他', value: 'other' },
];

// ── component ──

export default function ChannelPage() {
  const { channel } = useParams<{ channel: string }>();

  // ── local state ──
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [ordering, setOrdering] = useState('');

  // ── filter state ──
  const [txType, setTxType] = useState<string>('');
  const [timeRange, setTimeRange] = useState<[string, string] | null>(null);
  const [amountMin, setAmountMin] = useState<number | null>(null);
  const [amountMax, setAmountMax] = useState<number | null>(null);
  const [category, setCategory] = useState('');
  const [counterparty, setCounterparty] = useState('');
  const [tagIds, setTagIds] = useState<number[]>([]);

  // ── filter debounce states ──
  const [debouncedCategory, setDebouncedCategory] = useState('');
  const [debouncedCounterparty, setDebouncedCounterparty] = useState('');

  // ── available tags ──
  const { data: tagsResponse } = useTags();
  const availableTags = tagsResponse?.results ?? [];

  // validate channel
  const isValidChannel = channel != null && VALID_CHANNELS.includes(channel as (typeof VALID_CHANNELS)[number]);
  const platform = isValidChannel ? CHANNEL_PLATFORM[channel] : undefined;
  const title = isValidChannel ? CHANNEL_LABELS[channel] : '未知渠道';

  // ── debounced search (300ms) ──
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // ── debounced filters (500ms) ──
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedCategory(category);
      setPage(1);
    }, 500);
    return () => clearTimeout(timer);
  }, [category]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedCounterparty(counterparty);
      setPage(1);
    }, 500);
    return () => clearTimeout(timer);
  }, [counterparty]);

  // ── has active filters ──
  const hasFilters =
    txType !== '' ||
    timeRange != null ||
    amountMin != null ||
    amountMax != null ||
    debouncedCategory !== '' ||
    debouncedCounterparty !== '' ||
    tagIds.length > 0;

  // ── clear all filters ──
  const clearFilters = () => {
    setTxType('');
    setTimeRange(null);
    setAmountMin(null);
    setAmountMax(null);
    setCategory('');
    setCounterparty('');
    setTagIds([]);
    setPage(1);
  };

  // ── query params ──
  const queryParams: TransactionQueryParams = useMemo(
    () => ({
      platform,
      search: debouncedSearch || undefined,
      ordering: ordering || undefined,
      page,
      page_size: pageSize,
      tx_type: txType || undefined,
      time_after: timeRange?.[0],
      time_before: timeRange?.[1],
      amount_min: amountMin ?? undefined,
      amount_max: amountMax ?? undefined,
      category: debouncedCategory || undefined,
      counterparty: debouncedCounterparty || undefined,
      tag_ids: tagIds.length > 0 ? tagIds.join(',') : undefined,
    }),
    [
      platform,
      debouncedSearch,
      ordering,
      page,
      pageSize,
      txType,
      timeRange,
      amountMin,
      amountMax,
      debouncedCategory,
      debouncedCounterparty,
      tagIds,
    ],
  );

  // ── data fetching ──
  const { data: response, isLoading } = useTransactions(queryParams);

  const transactions = response?.results ?? [];
  const total = response?.count ?? 0;

  // ── handlers ──
  const handlePageChange = (newPage: number, newPageSize: number) => {
    if (newPageSize !== pageSize) {
      setPageSize(newPageSize);
      setPage(1);
    } else {
      setPage(newPage);
    }
  };

  const handleSearch = (value: string) => {
    setSearch(value);
  };

  const handleSort = (field: string, direction: 'asc' | 'desc') => {
    const orderingStr = direction === 'desc' ? `-${field}` : field;
    setOrdering(orderingStr);
  };

  // ── filter panel ──
  const filterPanel = (
    <Collapse
      items={[
        {
          key: 'filters',
          label: (
            <Space>
              <FilterOutlined />
              <span>高级筛选</span>
              {hasFilters && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  (已激活)
                </Text>
              )}
            </Space>
          ),
          extra: hasFilters ? (
            <Button size="small" icon={<ClearOutlined />} onClick={clearFilters}>
              清除
            </Button>
          ) : null,
          children: (
            <div>
              <Row gutter={[16, 16]}>
                <Col xs={24} sm={12} md={8}>
                  <div>
                    <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
                      交易类型
                    </Text>
                    <Select
                      value={txType}
                      onChange={(val) => {
                        setTxType(val);
                        setPage(1);
                      }}
                      options={TX_TYPE_OPTIONS}
                      style={{ width: '100%' }}
                      allowClear
                    />
                  </div>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <div>
                    <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
                      时间范围
                    </Text>
                    <RangePicker
                      value={null}
                      onChange={(dates) => {
                        if (dates && dates[0] && dates[1]) {
                          setTimeRange([dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]);
                        } else {
                          setTimeRange(null);
                        }
                        setPage(1);
                      }}
                      style={{ width: '100%' }}
                      placeholder={['开始日期', '结束日期']}
                    />
                  </div>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <div>
                    <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
                      标签筛选
                    </Text>
                    <Select
                      mode="multiple"
                      value={tagIds}
                      onChange={(vals) => {
                        setTagIds(vals);
                        setPage(1);
                      }}
                      options={availableTags.map((t) => ({ label: t.name, value: t.id }))}
                      style={{ width: '100%' }}
                      placeholder="选择标签"
                      allowClear
                      maxTagCount={3}
                      filterOption={(input, option) =>
                        (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                      }
                    />
                  </div>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <div>
                    <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
                      金额范围
                    </Text>
                    <Space.Compact style={{ width: '100%' }}>
                      <InputNumber
                        placeholder="最低"
                        value={amountMin}
                        onChange={(val) => {
                          setAmountMin(val);
                          setPage(1);
                        }}
                        style={{ width: '50%' }}
                        prefix="¥"
                      />
                      <InputNumber
                        placeholder="最高"
                        value={amountMax}
                        onChange={(val) => {
                          setAmountMax(val);
                          setPage(1);
                        }}
                        style={{ width: '50%' }}
                        prefix="¥"
                      />
                    </Space.Compact>
                  </div>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <div>
                    <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
                      分类
                    </Text>
                    <Input
                      placeholder="模糊搜索分类..."
                      value={category}
                      onChange={(e) => setCategory(e.target.value)}
                      allowClear
                    />
                  </div>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <div>
                    <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
                      交易对方
                    </Text>
                    <Input
                      placeholder="模糊搜索交易对方..."
                      value={counterparty}
                      onChange={(e) => setCounterparty(e.target.value)}
                      allowClear
                    />
                  </div>
                </Col>
              </Row>
            </div>
          ),
        },
      ]}
      style={{ marginBottom: 16 }}
      defaultActiveKey={hasFilters ? ['filters'] : undefined}
    />
  );

  // ── render ──
  return (
    <div style={{ padding: '0 0 24px' }}>
      <Title level={3} style={{ marginBottom: 24 }}>
        {title}
      </Title>
      {!isLoading && total === 0 && !debouncedSearch && !hasFilters ? (
        <EmptyState
          description={`暂无${CHANNEL_LABELS[channel ?? ''] ?? '渠道'}账单数据，请先导入账单文件。`}
        />
      ) : (
        <>
          {filterPanel}
          <ChannelTable
            data={transactions}
            loading={isLoading}
            pagination={{ page, pageSize, total }}
            onPageChange={handlePageChange}
            onSearch={handleSearch}
            onSort={handleSort}
            channel={channel as 'alipay' | 'wechat' | 'boc'}
            enableVirtual={pageSize >= 100}
          />
        </>
      )}
    </div>
  );
}
