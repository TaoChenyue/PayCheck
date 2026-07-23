import { Outlet } from 'react-router-dom';
import { Layout, theme } from 'antd';
import { useUIStore } from '@/stores/uiStore';
import SideMenu from './SideMenu';

const { Header, Sider, Content } = Layout;

export default function AppLayout() {
  const siderCollapsed = useUIStore((s) => s.siderCollapsed);
  const setSiderCollapsed = useUIStore((s) => s.setSiderCollapsed);
  const { token } = theme.useToken();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={siderCollapsed}
        onCollapse={setSiderCollapsed}
        theme="light"
      >
        <SideMenu />
      </Sider>
      <Layout>
        <Header
          style={{
            background: token.colorBgContainer,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            display: 'flex',
            alignItems: 'center',
            padding: `0 ${token.paddingLG}px`,
            height: token.controlHeightLG,
          }}
        >
          <h1
            style={{
              margin: 0,
              fontSize: token.fontSizeXL,
              fontWeight: 600,
              color: token.colorTextHeading,
            }}
          >
            PayCheck 账单管理
          </h1>
        </Header>
        <Content
          style={{
            margin: token.marginLG,
            padding: token.paddingLG,
            background: token.colorBgContainer,
            borderRadius: token.borderRadiusLG,
            minHeight: 280,
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
