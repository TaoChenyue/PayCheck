import { useMemo, useState, useCallback } from 'react';
import {
  createColumnHelper,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  flexRender,
  type SortingState,
} from '@tanstack/react-table';
import { Table, Input, Button, Dropdown, Tag, Space, Typography, Checkbox } from 'antd';
import type { MenuProps } from 'antd';
import { SearchOutlined, SettingOutlined } from '@ant-design/icons';
import type { Transaction } from '@/types';

const { Text } = Typography;

// ── column helper ──

const columnHelper = createColumnHelper<Transaction>();

// ── exported column definitions ──

export const TRANSACTION_COLUMNS = [
  columnHelper.accessor('time', {
    id: 'time',
    header: '交易时间',
    enableSorting: true,
  }),
  columnHelper.accessor('category', {
    id: 'category',
    header: '分类',
    enableSorting: true,
  }),
  columnHelper.accessor('counterparty', {
    id: 'counterparty',
    header: '交易对方',
    enableSorting: true,
  }),
  columnHelper.accessor('description', {
    id: 'description',
    header: '商品说明',
    enableSorting: false,
  }),
  columnHelper.accessor('amount', {
    id: 'amount',
    header: '金额',
    enableSorting: true,
    cell: (info) => {
      const raw = info.getValue();
      const isExpense = raw < 0;
      const formatted = new Intl.NumberFormat('zh-CN', {
        style: 'currency',
        currency: 'CNY',
        minimumFractionDigits: 2,
      }).format(Math.abs(raw));
      return (
        <Text style={{ color: isExpense ? '#ff4d4f' : '#52c41a' }}>
          {isExpense ? '-' : ''}{formatted}
        </Text>
      );
    },
  }),
  columnHelper.accessor('tx_type', {
    id: 'tx_type',
    header: '类型',
    enableSorting: true,
  }),
  columnHelper.accessor('payment_method', {
    id: 'payment_method',
    header: '支付方式',
    enableSorting: true,
  }),
  columnHelper.accessor('tags', {
    id: 'tags',
    header: '标签',
    enableSorting: false,
    cell: (info) => {
      const tags = info.getValue();
      if (tags.length === 0) return null;
      return (
        <Space wrap size={[0, 4]}>
          {tags.map((tag) => (
            <Tag key={tag.id}>{tag.name}</Tag>
          ))}
        </Space>
      );
    },
  }),
];

export const BANK_COLUMNS = [
  columnHelper.accessor('balance', {
    id: 'balance',
    header: '余额',
    enableSorting: true,
    cell: (info) => {
      const val = info.getValue();
      return new Intl.NumberFormat('zh-CN', {
        style: 'currency',
        currency: 'CNY',
        minimumFractionDigits: 2,
      }).format(val);
    },
  }),
  columnHelper.accessor('currency', {
    id: 'currency',
    header: '币种',
    enableSorting: false,
  }),
];

// ── props ──

interface TransactionTableProps {
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
  isBank?: boolean;
  /** Enable virtual scrolling for large datasets (pageSize >= 100) */
  enableVirtual?: boolean;
}

// ── component ──

export default function TransactionTable({
  data,
  loading,
  pagination,
  onPageChange,
  onSearch,
  onSort,
  isBank = false,
  enableVirtual = false,
}: TransactionTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchValue, setSearchValue] = useState('');
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>({});

  // merge bank columns when needed
  const columns = useMemo(() => {
    const base = [...TRANSACTION_COLUMNS];
    if (isBank) {
      base.push(...BANK_COLUMNS);
    }
    return base;
  }, [isBank]);

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      columnVisibility,
    },
    onSortingChange: (updater) => {
      const next = typeof updater === 'function' ? updater(sorting) : updater;
      setSorting(next);
      if (next.length > 0) {
        onSort(next[0].id, next[0].desc ? 'desc' : 'asc');
      }
    },
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualSorting: true,
  });

  const handleSearch = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = e.target.value;
      setSearchValue(val);
      onSearch(val);
    },
    [onSearch],
  );

  // Ant Design columns — mapped from TanStack Table flat headers
  const antdColumns = useMemo(() => {
    return table.getFlatHeaders()
      .filter((header) => header.column.getIsVisible())
      .map((header) => {
        const canSort = header.column.getCanSort();
        const sortDir = header.column.getIsSorted();
        return {
          title: (
            <span
              onClick={canSort ? () => header.column.toggleSorting() : undefined}
              style={
                canSort
                  ? { cursor: 'pointer', userSelect: 'none' as const }
                  : undefined
              }
            >
              {flexRender(header.column.columnDef.header, header.getContext())}
              {sortDir === 'asc' && (
                <span style={{ marginLeft: 4, fontSize: 11 }}>▲</span>
              )}
              {sortDir === 'desc' && (
                <span style={{ marginLeft: 4, fontSize: 11 }}>▼</span>
              )}
            </span>
          ),
          dataIndex: header.column.id,
          key: header.column.id,
          render: (_: unknown, record: Record<string, unknown>) => {
            const rendered = record._rendered as
              | Record<string, React.ReactNode>
              | undefined;
            return rendered?.[header.column.id] ?? null;
          },
        };
      });
  }, [table]);

  // dataSource with pre-rendered cells for TanStack → Ant Design bridge
  const dataSource = useMemo(() => {
    return table.getRowModel().rows.map((row) => {
      const rendered: Record<string, React.ReactNode> = {};
      row.getVisibleCells().forEach((cell) => {
        rendered[cell.column.id] = flexRender(
          cell.column.columnDef.cell,
          cell.getContext(),
        );
      });
      return {
        ...row.original,
        key: row.original.id,
        _rendered: rendered,
      };
    });
  }, [table.getRowModel().rows]);

  // column visibility dropdown items
  const visibilityItems: MenuProps['items'] = table.getAllColumns().map((col) => {
    const headerLabel =
      typeof col.columnDef.header === 'string' ? col.columnDef.header : col.id;
    return {
      key: col.id,
      label: (
        <Checkbox
          checked={col.getIsVisible()}
          onChange={() => col.toggleVisibility()}
        >
          {headerLabel}
        </Checkbox>
      ),
    };
  });

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <Input
          placeholder="搜索交易对方或商品说明..."
          prefix={<SearchOutlined />}
          value={searchValue}
          onChange={handleSearch}
          style={{ width: 320 }}
          allowClear
        />
        <Dropdown menu={{ items: visibilityItems }} trigger={['click']}>
          <Button icon={<SettingOutlined />}>列显示</Button>
        </Dropdown>
      </div>
      <Table
        columns={antdColumns}
        dataSource={dataSource}
        loading={loading}
        pagination={{
          current: pagination.page,
          pageSize: pagination.pageSize,
          total: pagination.total,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100', '200'],
          showTotal: (total: number) => `共 ${total} 条`,
          onChange: onPageChange,
        }}
        scroll={{ x: 'max-content', y: enableVirtual ? 600 : undefined }}
        virtual={enableVirtual}
        size="middle"
        rowKey="key"
      />
    </div>
  );
}
