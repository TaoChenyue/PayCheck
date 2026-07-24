import TransactionTable from '@/components/tables/TransactionTable';
import type { Transaction } from '@/types';

interface ChannelTableProps {
  data: Transaction[];
  loading: boolean;
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
  onPageChange: (page: number, pageSize: number) => void;
  onSearch: (search: string) => void;
  onSort: (field: string, direction: 'asc' | 'desc') => void;
  channel: 'alipay' | 'wechat' | 'bank';
}

/** 渠道账单表格 — 对 TransactionTable 的渠道适配封装 */
export default function ChannelTable({
  channel,
  ...rest
}: ChannelTableProps) {
  return <TransactionTable {...rest} isBank={channel === 'bank'} />;
}
