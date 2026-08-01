import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/api/client';
import type {
  Transaction,
  TransactionQueryParams,
  BatchTagsRequest,
  BatchTagsResponse,
  PaginatedResponse,
} from '@/types';

const TRANSACTIONS_URL = '/transactions/';

async function fetchTransactions(params: TransactionQueryParams): Promise<PaginatedResponse<Transaction>> {
  const { data } = await apiClient.get(TRANSACTIONS_URL, { params });
  return data;
}

async function fetchTransaction(id: number): Promise<Transaction> {
  const { data } = await apiClient.get(`${TRANSACTIONS_URL}${id}/`);
  return data;
}

async function deleteTransaction(id: number): Promise<void> {
  await apiClient.delete(`${TRANSACTIONS_URL}${id}/`);
}

async function setTransactionTags(id: number, tagIds: number[]): Promise<Transaction> {
  const { data } = await apiClient.post(`${TRANSACTIONS_URL}${id}/tags/`, { tag_ids: tagIds });
  return data;
}

async function batchSetTags(req: BatchTagsRequest): Promise<BatchTagsResponse> {
  const { data } = await apiClient.post(`${TRANSACTIONS_URL}batch-tags/`, req);
  return data;
}

// ── Hooks ──

export function useTransactions(params: TransactionQueryParams) {
  return useQuery({
    queryKey: ['transactions', params],
    queryFn: () => fetchTransactions(params),
    placeholderData: (prev) => prev,
    staleTime: 30_000,    // 30s before refetch — data is static until new import
    gcTime: 5 * 60_000,   // 5min garbage collection
    retry: 2,
  });
}

export function useTransaction(id: number) {
  return useQuery({
    queryKey: ['transactions', id],
    queryFn: () => fetchTransaction(id),
    enabled: !!id,
    staleTime: 60_000,
    gcTime: 10 * 60_000,
    retry: 2,
  });
}

export function useDeleteTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteTransaction,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['transactions'] }); },
  });
}

export function useSetTransactionTags() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, tagIds }: { id: number; tagIds: number[] }) => setTransactionTags(id, tagIds),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['transactions'] }); },
  });
}

export function useBatchSetTags() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: batchSetTags,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['transactions'] }); },
  });
}
