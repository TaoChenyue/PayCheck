import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/api/client';
import type { Tag, PaginatedResponse } from '@/types';

const TAGS_URL = '/tags/';

async function fetchTags(): Promise<PaginatedResponse<Tag>> {
  const { data } = await apiClient.get(TAGS_URL, { params: { page_size: 200 } });
  return data;
}

async function createTag(name: string): Promise<Tag> {
  const { data } = await apiClient.post(TAGS_URL, { name });
  return data;
}

async function updateTag(id: number, name: string): Promise<Tag> {
  const { data } = await apiClient.patch(`${TAGS_URL}${id}/`, { name });
  return data;
}

async function deleteTag(id: number): Promise<void> {
  await apiClient.delete(`${TAGS_URL}${id}/`);
}

export function useTags() {
  return useQuery({
    queryKey: ['tags'],
    queryFn: fetchTags,
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  });
}

export function useCreateTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createTag,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['tags'] }); },
  });
}

export function useUpdateTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => updateTag(id, name),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['tags'] }); },
  });
}

export function useDeleteTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteTag,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['tags'] }); },
  });
}
