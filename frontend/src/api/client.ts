import axios from 'axios';
import { message } from 'antd';

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const errorData = error.response?.data;

    // Use backend unified error format if available
    const errorMsg =
      errorData?.message
      || errorData?.detail
      || error.message
      || '请求失败';

    // Suppress toast for specific status codes (handled locally by components)
    const suppressToast = error.config?.suppressToast;

    if (!suppressToast) {
      switch (status) {
        case 400:
          message.warning(errorMsg);
          break;
        case 404:
          message.info(errorMsg);
          break;
        case 500:
          message.error(errorMsg);
          break;
        default:
          if (error.code === 'ECONNABORTED') {
            message.error('请求超时，请检查网络连接');
          } else if (!error.response) {
            message.error('网络连接失败，请检查后端服务是否启动');
          } else {
            message.error(errorMsg);
          }
      }
    }

    console.error('API Error:', { status, message: errorMsg, url: error.config?.url });
    return Promise.reject(error);
  },
);

export default apiClient;
