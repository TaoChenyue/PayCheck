import { useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Menu } from 'antd';
import type { MenuProps } from 'antd';
import {
  ImportOutlined,
  BankOutlined,
  AlipayOutlined,
  WechatOutlined,
  DashboardOutlined,
  PieChartOutlined,
  FilePdfOutlined,
} from '@ant-design/icons';
function getOpenKeys(pathname: string): string[] {
  if (pathname === '/import' || pathname.startsWith('/import/') || pathname.startsWith('/channels')) {
    return ['/data'];
  }
  if (pathname === '/dashboard' || pathname === '/analysis') {
    return ['/analyze'];
  }
  return [];
}

const menuItems: MenuProps['items'] = [
  {
    key: '/data',
    icon: <ImportOutlined />,
    label: '数据管理',
    children: [
      {
        key: '/import',
        icon: <ImportOutlined />,
        label: '数据导入',
      },
      {
        key: '/import/pdf-to-csv',
        icon: <FilePdfOutlined />,
        label: 'PDF 转 CSV',
      },
      {
        key: '/channels/alipay',
        icon: <AlipayOutlined />,
        label: '支付宝账单',
      },
      {
        key: '/channels/wechat',
        icon: <WechatOutlined />,
        label: '微信账单',
      },
      {
        key: '/channels/boc',
        icon: <BankOutlined />,
        label: '银行账单',
      },
    ],
  },
  {
    key: '/analyze',
    icon: <PieChartOutlined />,
    label: '分析',
    children: [
      {
        key: '/dashboard',
        icon: <DashboardOutlined />,
        label: '概览仪表盘',
      },
      {
        key: '/analysis',
        icon: <PieChartOutlined />,
        label: '详细分析',
      },
    ],
  },
];

export default function SideMenu() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const selectedKeys = useMemo<string[]>(() => [pathname], [pathname]);
  const openKeys = useMemo<string[]>(() => getOpenKeys(pathname), [pathname]);

  const handleClick: MenuProps['onClick'] = ({ key }) => {
    navigate(key);
  };

  return (
    <Menu
      mode="inline"
      items={menuItems}
      selectedKeys={selectedKeys}
      openKeys={openKeys}
      onClick={handleClick}
      style={{ height: '100%', borderInlineEnd: 0 }}
    />
  );
}
