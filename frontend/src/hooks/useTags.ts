import { useQuery } from '@tanstack/react-query';
import apiClient from '@/api/client';
import type { Tag, PaginatedResponse } from '@/types';

const TAGS_URL = '/transactions/tags/';

async function fetchTags(): Promise<PaginatedResponse<Tag>> {
  const { data } = await apiClient.get(TAGS_URL, { params: { page_size: 200 } });
  return data;
}

export function useTags() {
  return useQuery({
    queryKey: ['tags'],
    queryFn: fetchTags,
  });
}
