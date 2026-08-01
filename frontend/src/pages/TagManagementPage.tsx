import { useState } from 'react';
import { Table, Button, Modal, Input, Space, Popconfirm, Typography, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, TagsOutlined } from '@ant-design/icons';
import { useTags, useCreateTag, useUpdateTag, useDeleteTag } from '@/hooks/useTags';
import type { Tag } from '@/types';
import type { ColumnsType } from 'antd/es/table';

const { Title } = Typography;

export default function TagManagementPage() {
  const { data: tagsResponse, isLoading } = useTags();
  const createTag = useCreateTag();
  const updateTag = useUpdateTag();
  const deleteTag = useDeleteTag();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingTag, setEditingTag] = useState<Tag | null>(null);
  const [tagName, setTagName] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const tags = tagsResponse?.results ?? [];

  const openCreateModal = () => {
    setEditingTag(null);
    setTagName('');
    setModalOpen(true);
  };

  const openEditModal = (tag: Tag) => {
    setEditingTag(tag);
    setTagName(tag.name);
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const trimmed = tagName.trim();
    if (!trimmed) {
      message.warning('标签名称不能为空');
      return;
    }
    setSubmitting(true);
    try {
      if (editingTag) {
        await updateTag.mutateAsync({ id: editingTag.id, name: trimmed });
        message.success('标签已更新');
      } else {
        await createTag.mutateAsync(trimmed);
        message.success('标签已创建');
      }
      setModalOpen(false);
      setTagName('');
      setEditingTag(null);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    await deleteTag.mutateAsync(id);
    message.success('标签已删除');
  };

  const columns: ColumnsType<Tag> = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: '标签名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: unknown, record: Tag) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEditModal(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确认删除"
            description={`确定要删除标签「${record.name}」吗？`}
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>
          <TagsOutlined style={{ marginRight: 8 }} />
          标签管理
        </Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
          新建标签
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={tags}
        loading={isLoading}
        rowKey="id"
        pagination={false}
        size="middle"
      />

      <Modal
        title={editingTag ? '编辑标签' : '新建标签'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => {
          setModalOpen(false);
          setEditingTag(null);
          setTagName('');
        }}
        confirmLoading={submitting}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Input
          placeholder="请输入标签名称"
          value={tagName}
          onChange={(e) => setTagName(e.target.value)}
          onPressEnter={handleSubmit}
          maxLength={50}
          showCount
        />
      </Modal>
    </div>
  );
}
