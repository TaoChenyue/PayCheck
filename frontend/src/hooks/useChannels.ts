import { useQuery } from '@tanstack/react-query';
import apiClient from '@/api/client';
import type { ChannelTx, ChannelType, PaginatedResponse } from '@/types';

const CHANNEL_URLS: Record<ChannelType, string> = {
  alipay: '/channels/alipay/',
  wechat: '/channels/wechat/',
  bank: '/channels/boc/',
};

async function fetchChannelTxs(
  channel: ChannelType,
  params: Record<string, string | number | undefined>,
): Promise<PaginatedResponse<ChannelTx>> {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== ''),
  );
  const { data } = await apiClient.get(CHANNEL_URLS[channel], { params: cleanParams });
  return data;
}

export function useChannelTxs(channel: ChannelType, params: Record<string, string | number | undefined> = {}) {
  return useQuery({
    queryKey: ['channels', channel, params],
    queryFn: () => fetchChannelTxs(channel, params),
  });
}
