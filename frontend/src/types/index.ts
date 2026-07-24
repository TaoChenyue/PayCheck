// ── Models ──

export interface Tag {
  id: number;
  name: string;
}

export interface Transaction {
  id: number;
  platform: 'alipay' | 'wechat' | 'boc';
  time: string;
  category: string;
  counterparty: string;
  description: string;
  amount: number;
  tx_type: string;
  payment_method: string;
  balance: number;
  currency: string;
  branch: string;
  cp_account: string;
  cp_bank: string;
  source_channel: string;
  source_id: number;
  row_hash: string;
  tags: Tag[];
  created_at: string;
}

export interface TransactionWrite {
  platform: string;
  time: string;
  category: string;
  counterparty: string;
  description: string;
  amount: number;
  tx_type: string;
  payment_method: string;
  balance: number;
  currency: string;
  branch: string;
  cp_account: string;
  cp_bank: string;
  source_channel: string;
  source_id: number;
  row_hash: string;
}

export interface ChannelTx {
  id: number;
  time: string;
  category: string;
  counterparty: string;
  description: string;
  amount: number;
  tx_type: string;
  payment_method: string;
  balance?: number;
  currency?: string;
  branch?: string;
  cp_account?: string;
  cp_bank?: string;
  created_at: string;
}

// ── Import ──

export type FileType = 'alipay_csv' | 'wechat_xlsx' | 'boc_pdf' | 'boc_csv';
export type JobStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type ChannelType = 'alipay' | 'wechat' | 'boc';

export interface ImportFile {
  id: number;
  filename: string;
  file_type: FileType;
  status: JobStatus;
  error_msg: string;
  created_at: string;
}

export interface ImportJob {
  id: number;
  status: JobStatus;
  total_files: number;
  processed: number;
  created_at: string;
  completed_at: string | null;
  files: ImportFile[];
}

export interface ImportUploadResponse {
  job_id: number;
  status: JobStatus;
  total_files: number;
  files: Pick<ImportFile, 'id' | 'filename' | 'status'>[];
}

// ── Analysis ──

export interface SummaryData {
  period: {
    start: string;
    end: string;
  };
  summary: {
    total_expense: number;
    total_income: number;
    total_count: number;
    monthly_avg: number;
    wechat_total: number;
    alipay_total: number;
    boc_total: number;
    wechat_count: number;
    alipay_count: number;
    boc_count: number;
  };
  monthly: MonthlyItem[];
  categories: CategoryItem[];
  generated_at: string;
}

export interface MonthlyItem {
  month: string;
  expense: number;
  count: number;
  wechat: number;
  alipay: number;
  boc: number;
}

export interface CategoryItem {
  name: string;
  amount: number;
  count: number;
  pct: number;
}

export interface MonthlyData {
  month: string;
  expense: number;
  count: number;
}

export interface CategoryData {
  name: string;
  amount: number;
  count: number;
  pct: number;
}

// ── Pagination ──

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ── Query Params ──

export interface TransactionQueryParams {
  platform?: ChannelType;
  tx_type?: string;
  time_after?: string;
  time_before?: string;
  amount_min?: number;
  amount_max?: number;
  category?: string;
  counterparty?: string;
  search?: string;
  tag_ids?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
}

export interface BatchTagsRequest {
  transaction_ids: number[];
  tag_ids: number[];
}

export interface BatchTagsResponse {
  updated_transactions: number;
  tags_applied: number;
}
