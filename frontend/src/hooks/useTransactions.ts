import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/api/client';
import type {
  Transaction,
  TransactionWrite,
  TransactionQueryParams,
  BatchTagsRequest,
  BatchTagsResponse,
  PaginatedResponse,
} from '@/types';

const TRANSACTIONS_URL = '/transactions/transactions/';

async function fetchTransactions(params: TransactionQueryParams): Promise<PaginatedResponse<Transaction>> {
  const { data } = await apiClient.get(TRANSACTIONS_URL, { params });
  return data;
}

async function fetchTransaction(id: number): Promise<Transaction> {
  const { data } = await apiClient.get(`${TRANSACTIONS_URL}${id}/`);
  return data;
}

async function createTransaction(tx: TransactionWrite): Promise<Transaction> {
  const { data } = await apiClient.post(TRANSACTIONS_URL, tx);
  return data;
}

async function updateTransaction(id: number, tx: Partial<TransactionWrite>): Promise<Transaction> {
  const { data } = await apiClient.patch(`${TRANSACTIONS_URL}${id}/`, tx);
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
  });
}

export function useTransaction(id: number) {
  return useQuery({
    queryKey: ['transactions', id],
    queryFn: () => fetchTransaction(id),
    enabled: !!id,
  });
}

export function useCreateTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createTransaction,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['transactions'] }); },
  });
}

export function useUpdateTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<TransactionWrite> }) => updateTransaction(id, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['transactions'] }); },
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
