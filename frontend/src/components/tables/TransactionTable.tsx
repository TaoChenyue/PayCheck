import { useMemo, useState, useCallback } from 'react';
import {
  createColumnHelper,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  flexRender,
  type SortingState,
} from '@tanstack/react-table';
import {
  Table,
  Input,
  Button,
  Dropdown,
  Tag,
  Space,
  Typography,
  Checkbox,
  Popconfirm,
  Drawer,
  Descriptions,
  Select,
  Popover,
  message,
  Divider,
} from 'antd';
import type { MenuProps } from 'antd';
import {
  SearchOutlined,
  SettingOutlined,
  DeleteOutlined,
  TagsOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import type { Transaction, Tag as TagType } from '@/types';
import {
  useDeleteTransaction,
  useSetTransactionTags,
  useBatchSetTags,
  useTransaction,
} from '@/hooks/useTransactions';
import { useTags } from '@/hooks/useTags';

const { Text } = Typography;

// ── column helper ──

const columnHelper = createColumnHelper<Transaction>();

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

  // ── row selection ──
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  // ── detail drawer ──
  const [detailId, setDetailId] = useState<number | null>(null);
  const { data: detailTx, isLoading: detailLoading } = useTransaction(detailId ?? 0);

  // ── tag editor ──
  const [tagEditorOpen, setTagEditorOpen] = useState(false);
  const [editingTxId, setEditingTxId] = useState<number | null>(null);
  const [editingTagIds, setEditingTagIds] = useState<number[]>([]);

  // ── batch tag editor ──
  const [batchTagOpen, setBatchTagOpen] = useState(false);
  const [batchTagIds, setBatchTagIds] = useState<number[]>([]);

  // ── mutations ──
  const deleteMutation = useDeleteTransaction();
  const setTagsMutation = useSetTransactionTags();
  const batchTagsMutation = useBatchSetTags();

  // ── available tags ──
  const { data: tagsResponse } = useTags();
  const availableTags = tagsResponse?.results ?? [];

  // ── tag editor helpers ──
  const openTagEditor = useCallback((txId: number, currentTags: TagType[]) => {
    setEditingTxId(txId);
    setEditingTagIds(currentTags.map((t) => t.id));
    setTagEditorOpen(true);
  }, []);

  const handleSaveTags = useCallback(async () => {
    if (editingTxId == null) return;
    try {
      await setTagsMutation.mutateAsync({ id: editingTxId, tagIds: editingTagIds });
      message.success('标签已更新');
      setTagEditorOpen(false);
      setEditingTxId(null);
    } catch {
      // toast handled by axios interceptor
    }
  }, [editingTxId, editingTagIds, setTagsMutation]);

  const handleBatchTagsApply = useCallback(async () => {
    if (selectedRowKeys.length === 0 || batchTagIds.length === 0) {
      message.warning('请选择标签');
      return;
    }
    try {
      await batchTagsMutation.mutateAsync({
        transaction_ids: selectedRowKeys.map(Number),
        tag_ids: batchTagIds,
      });
      message.success(`已为 ${selectedRowKeys.length} 条交易打标签`);
      setBatchTagOpen(false);
      setBatchTagIds([]);
      setSelectedRowKeys([]);
    } catch {
      // toast handled by axios interceptor
    }
  }, [selectedRowKeys, batchTagIds, batchTagsMutation]);

  const handleDelete = useCallback(
    async (id: number) => {
      try {
        await deleteMutation.mutateAsync(id);
        message.success('交易已删除');
      } catch {
        // toast handled by axios interceptor
      }
    },
    [deleteMutation],
  );

  // ── tag selector content ──
  const tagSelectorContent = (
    <div style={{ width: 280 }}>
      <Select
        mode="multiple"
        style={{ width: '100%' }}
        placeholder="选择标签"
        value={editingTagIds}
        onChange={(vals) => setEditingTagIds(vals)}
        options={availableTags.map((t) => ({ label: t.name, value: t.id }))}
        filterOption={(input, option) =>
          (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
        }
      />
      <div style={{ marginTop: 12, textAlign: 'right' }}>
        <Button
          size="small"
          onClick={() => {
            setTagEditorOpen(false);
            setEditingTxId(null);
          }}
          style={{ marginRight: 8 }}
        >
          取消
        </Button>
        <Button type="primary" size="small" onClick={handleSaveTags} loading={setTagsMutation.isPending}>
          保存
        </Button>
      </div>
    </div>
  );

  const batchTagSelectorContent = (
    <div style={{ width: 300 }}>
      <Select
        mode="multiple"
        style={{ width: '100%' }}
        placeholder="选择要应用的标签"
        value={batchTagIds}
        onChange={(vals) => setBatchTagIds(vals)}
        options={availableTags.map((t) => ({ label: t.name, value: t.id }))}
        filterOption={(input, option) =>
          (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
        }
      />
      <div style={{ marginTop: 12, textAlign: 'right' }}>
        <Button
          size="small"
          onClick={() => {
            setBatchTagOpen(false);
            setBatchTagIds([]);
          }}
          style={{ marginRight: 8 }}
        >
          取消
        </Button>
        <Button
          type="primary"
          size="small"
          onClick={handleBatchTagsApply}
          loading={batchTagsMutation.isPending}
        >
          应用 ({selectedRowKeys.length} 条)
        </Button>
      </div>
    </div>
  );

  // ── column definitions ──

  const TRANSACTION_COLUMNS = useMemo(
    () => [
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
          const txId = info.row.original.id;
          return (
            <Popover
              open={tagEditorOpen && editingTxId === txId}
              onOpenChange={(open) => {
                if (!open) {
                  setTagEditorOpen(false);
                  setEditingTxId(null);
                }
              }}
              content={tagSelectorContent}
              title="编辑标签"
              trigger="click"
            >
              <span
                style={{ cursor: 'pointer', minWidth: 24, display: 'inline-block' }}
                onClick={(e) => {
                  e.stopPropagation();
                  openTagEditor(txId, tags);
                }}
              >
                {tags.length === 0 ? (
                  <Tag style={{ borderStyle: 'dashed' }} icon={<PlusOutlined />}>
                    添加标签
                  </Tag>
                ) : (
                  <Space wrap size={[0, 4]}>
                    {tags.map((tag) => (
                      <Tag key={tag.id}>{tag.name}</Tag>
                    ))}
                  </Space>
                )}
              </span>
            </Popover>
          );
        },
      }),
      columnHelper.display({
        id: 'actions',
        header: '操作',
        cell: (info) => (
          <Popconfirm
            title="确认删除"
            description="确定要删除这笔交易吗？此操作不可撤销。"
            onConfirm={() => handleDelete(info.row.original.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={(e) => e.stopPropagation()}
            >
              删除
            </Button>
          </Popconfirm>
        ),
      }),
    ],
    [tagEditorOpen, editingTxId, tagSelectorContent, openTagEditor, handleDelete],
  );

  const BANK_COLUMNS = useMemo(
    () => [
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
    ],
    [],
  );

  // merge bank columns when needed
  const columns = useMemo(() => {
    const base = [...TRANSACTION_COLUMNS];
    if (isBank) {
      base.splice(base.length - 1, 0, ...BANK_COLUMNS); // insert before actions column
    }
    return base;
  }, [isBank, TRANSACTION_COLUMNS, BANK_COLUMNS]);

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
    return table
      .getFlatHeaders()
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
              {sortDir === 'asc' && <span style={{ marginLeft: 4, fontSize: 11 }}>▲</span>}
              {sortDir === 'desc' && <span style={{ marginLeft: 4, fontSize: 11 }}>▼</span>}
            </span>
          ),
          dataIndex: header.column.id,
          key: header.column.id,
          render: (_: unknown, record: Record<string, unknown>) => {
            const rendered = record._rendered as Record<string, React.ReactNode> | undefined;
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
        rendered[cell.column.id] = flexRender(cell.column.columnDef.cell, cell.getContext());
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
    const headerLabel = typeof col.columnDef.header === 'string' ? col.columnDef.header : col.id;
    return {
      key: col.id,
      label: (
        <Checkbox checked={col.getIsVisible()} onChange={() => col.toggleVisibility()}>
          {headerLabel}
        </Checkbox>
      ),
    };
  });

  // detail drawer content
  const renderDetailDrawer = () => {
    if (!detailTx) return null;
    return (
      <Drawer
        title="交易详情"
        open={detailId != null}
        onClose={() => setDetailId(null)}
        width={480}
        destroyOnClose
      >
        {detailLoading ? (
          <Typography.Text type="secondary">加载中...</Typography.Text>
        ) : (
          <Descriptions column={1} bordered size="small" labelStyle={{ width: 100 }}>
            <Descriptions.Item label="交易时间">{detailTx.time}</Descriptions.Item>
            <Descriptions.Item label="平台">{detailTx.platform}</Descriptions.Item>
            <Descriptions.Item label="分类">{detailTx.category}</Descriptions.Item>
            <Descriptions.Item label="交易对方">{detailTx.counterparty}</Descriptions.Item>
            <Descriptions.Item label="商品说明">{detailTx.description}</Descriptions.Item>
            <Descriptions.Item label="金额">
              <Text style={{ color: detailTx.amount < 0 ? '#ff4d4f' : '#52c41a' }}>
                {new Intl.NumberFormat('zh-CN', {
                  style: 'currency',
                  currency: 'CNY',
                }).format(detailTx.amount)}
              </Text>
            </Descriptions.Item>
            <Descriptions.Item label="类型">{detailTx.tx_type}</Descriptions.Item>
            <Descriptions.Item label="支付方式">{detailTx.payment_method}</Descriptions.Item>
            {isBank && (
              <>
                <Descriptions.Item label="余额">
                  {new Intl.NumberFormat('zh-CN', {
                    style: 'currency',
                    currency: 'CNY',
                  }).format(detailTx.balance)}
                </Descriptions.Item>
                <Descriptions.Item label="币种">{detailTx.currency}</Descriptions.Item>
              </>
            )}
            <Descriptions.Item label="标签">
              {detailTx.tags.length > 0 ? (
                <Space wrap size={[0, 4]}>
                  {detailTx.tags.map((tag) => (
                    <Tag key={tag.id}>{tag.name}</Tag>
                  ))}
                </Space>
              ) : (
                <Text type="secondary">无</Text>
              )}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    );
  };

  return (
    <div>
      {/* batch action bar */}
      {selectedRowKeys.length > 0 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '8px 16px',
            marginBottom: 16,
            background: '#f6f3ff',
            borderRadius: 8,
            border: '1px solid #d9c8ff',
          }}
        >
          <Text strong style={{ marginRight: 16 }}>
            已选择 {selectedRowKeys.length} 条
          </Text>
          <Popover
            open={batchTagOpen}
            onOpenChange={(open) => {
              if (!open) {
                setBatchTagOpen(false);
                setBatchTagIds([]);
              }
            }}
            content={batchTagSelectorContent}
            title="批量打标签"
            trigger="click"
          >
            <Button icon={<TagsOutlined />} onClick={() => setBatchTagOpen(true)}>
              批量打标签
            </Button>
          </Popover>
          <Button
            style={{ marginLeft: 8 }}
            onClick={() => setSelectedRowKeys([])}
          >
            取消选择
          </Button>
        </div>
      )}

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
        rowSelection={{
          selectedRowKeys,
          onChange: (keys) => setSelectedRowKeys(keys),
          preserveSelectedRowKeys: false,
        }}
        onRow={(record) => ({
          onClick: () => setDetailId(record.id as number),
          style: { cursor: 'pointer' },
        })}
      />
      {renderDetailDrawer()}
    </div>
  );
}
