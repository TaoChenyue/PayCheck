import { useQuery } from '@tanstack/react-query';
import apiClient from '@/api/client';
import type { SummaryData, MonthlyData, CategoryData } from '@/types';

async function fetchSummary(): Promise<SummaryData> {
  const { data } = await apiClient.get('/analysis/summary/');
  return data;
}

async function fetchMonthly(platform?: string): Promise<MonthlyData[]> {
  const { data } = await apiClient.get('/analysis/monthly/', { params: platform ? { platform } : {} });
  return data;
}

async function fetchCategories(limit = 20): Promise<CategoryData[]> {
  const { data } = await apiClient.get('/analysis/categories/', { params: { limit } });
  return data;
}

export function useSummary() {
  return useQuery({
    queryKey: ['analysis', 'summary'],
    queryFn: fetchSummary,
  });
}

export function useMonthly(platform?: string) {
  return useQuery({
    queryKey: ['analysis', 'monthly', platform],
    queryFn: () => fetchMonthly(platform),
  });
}

export function useCategories(limit = 20) {
  return useQuery({
    queryKey: ['analysis', 'categories', limit],
    queryFn: () => fetchCategories(limit),
  });
}
