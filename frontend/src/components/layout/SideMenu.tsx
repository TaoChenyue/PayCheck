import { useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Menu } from 'antd';
import type { MenuProps } from 'antd';
import {
  ToolOutlined,
  FilePdfOutlined,
  BankOutlined,
  AlipayOutlined,
  WechatOutlined,
} from '@ant-design/icons';

const ROOT_KEYS = ['/tools', '/channels'] as const;

function getOpenKeys(pathname: string): string[] {
  for (const key of ROOT_KEYS) {
    if (pathname.startsWith(key)) {
      return [key];
    }
  }
  return [];
}

const menuItems: MenuProps['items'] = [
  {
    key: '/tools',
    icon: <ToolOutlined />,
    label: '工具',
    children: [
      {
        key: '/tools/pdf-to-csv',
        icon: <FilePdfOutlined />,
        label: 'PDF转CSV',
      },
    ],
  },
  {
    key: '/channels',
    icon: <BankOutlined />,
    label: '账单渠道',
    children: [
      {
        key: '/channels/alipay',
        icon: <AlipayOutlined />,
        label: '支付宝',
      },
      {
        key: '/channels/wechat',
        icon: <WechatOutlined />,
        label: '微信',
      },
      {
        key: '/channels/boc',
        icon: <BankOutlined />,
        label: '中国银行',
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
