import { useState, useMemo, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Typography } from 'antd';
import { useTransactions } from '@/hooks/useTransactions';
import ChannelTable from '@/components/tables/ChannelTable';
import type { TransactionQueryParams, ChannelType } from '@/types';

const { Title } = Typography;

// ── channel metadata ──

const CHANNEL_LABELS: Record<string, string> = {
  alipay: '支付宝账单',
  wechat: '微信账单',
  boc: '中国银行账单',
};

const CHANNEL_PLATFORM: Record<string, ChannelType> = {
  alipay: 'alipay',
  wechat: 'wechat',
  bank: 'bank',
};

const VALID_CHANNELS = ['alipay', 'wechat', 'bank'] as const;

// ── component ──

export default function ChannelPage() {
  const { channel } = useParams<{ channel: string }>();

  // ── local state ──
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [ordering, setOrdering] = useState('');

  // validate channel
  const isValidChannel = channel != null && VALID_CHANNELS.includes(channel as typeof VALID_CHANNELS[number]);
  const platform = isValidChannel ? CHANNEL_PLATFORM[channel] : undefined;
  const title = isValidChannel ? CHANNEL_LABELS[channel] : '未知渠道';

  // ── debounced search (300ms) ──
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1); // reset to page 1 on new search
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // ── query params ──
  const queryParams: TransactionQueryParams = useMemo(
    () => ({
      platform,
      search: debouncedSearch || undefined,
      ordering: ordering || undefined,
      page,
      page_size: pageSize,
    }),
    [platform, debouncedSearch, ordering, page, pageSize],
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

  // ── render ──
  return (
    <div style={{ padding: '0 0 24px' }}>
      <Title level={3} style={{ marginBottom: 24 }}>
        {title}
      </Title>
      <ChannelTable
        data={transactions}
        loading={isLoading}
        pagination={{ page, pageSize, total }}
        onPageChange={handlePageChange}
        onSearch={handleSearch}
        onSort={handleSort}
        channel={channel as 'alipay' | 'wechat' | 'bank'}
      />
    </div>
  );
}
