import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/api/client';
import type {
  ImportJob,
  ImportUploadResponse,
  ChannelType,
  PaginatedResponse,
} from '@/types';

const JOBS_URL = '/import/jobs/';

async function fetchJobs(): Promise<PaginatedResponse<ImportJob>> {
  const { data } = await apiClient.get(JOBS_URL);
  return data;
}

async function fetchJob(id: number): Promise<ImportJob> {
  const { data } = await apiClient.get(`${JOBS_URL}${id}/`);
  return data;
}

async function uploadFiles(channel: ChannelType, files: File[]): Promise<ImportUploadResponse> {
  const formData = new FormData();
  formData.append('channel', channel);
  files.forEach((f) => formData.append('files', f));
  const { data } = await apiClient.post('/import/upload/', formData);
  return data;
}

// ── Hooks ──

export function useImportJobs() {
  return useQuery({
    queryKey: ['importJobs'],
    queryFn: fetchJobs,
    staleTime: 10_000,     // 10s — import jobs change frequently during processing
    gcTime: 5 * 60_000,
    retry: 2,
  });
}

export function useImportJob(id: number, { enabled = true, refetchInterval }: {
  enabled?: boolean;
  refetchInterval?: number | false;
} = {}) {
  return useQuery({
    queryKey: ['importJobs', id],
    queryFn: () => fetchJob(id),
    enabled,
    refetchInterval,
    staleTime: 0,           // always fresh during polling
    gcTime: 10 * 60_000,
    retry: 2,
  });
}

export function useUploadFiles() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ channel, files }: { channel: ChannelType; files: File[] }) => uploadFiles(channel, files),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['importJobs'] }); },
  });
}
