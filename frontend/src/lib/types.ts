export const REVIEW_STATUSES = ['pending', 'in_progress', 'completed', 'failed'] as const;
export type ReviewStatus = typeof REVIEW_STATUSES[number];


export const LANGUAGES = [
  { value: "python", label: 'Python' },
  { value: "javascript", label: "JavaScript" },
  { value: "typescript", label: "TypeScript" },
  { value: "go", label: "Go" },
  { value: "java", label: "Java" },
  { value: "csharp", label: "C#" },
  { value: "cpp", label: "C++" },
  { value: "rust", label: "Rust" }
] as const;

export type Language = typeof LANGUAGES[number];

export type Severity = 'low' | 'med' | 'high';

export interface Issue {
  title: string;
  detail?: string;
  severity?: Severity;
  category?: string;
}

export interface Review {
  id: string;
  status: ReviewStatus;
  created_at: string;
  updated_at: string;
  language: string;
  score?: number | null;
  issues?: Issue[];
  security?: Issue[];
  performance?: Issue[];
  suggestions?: string[];
  error?: string | null;
}

export interface StatsResponse {
  total: number;
  avg_score: number | null;
  common_issues: string[];
}

export interface ListReviewsParams {
  language?: string;
  status?: string;
  min_score?: number;
  max_score?: number;
  start_date?: string
  end_date?: string; 
  page?: number;
  page_size?: number;
}

export interface PaginatedReviewsResponse {
  items: Review[];
  total: number;
  page: number;
  page_size: number;
}

export interface GetStatsParams {
  language?: string;
  start_date?: string
  end_date?: string; 
}

export interface SubmitPayload {
  language: string;
  code: string;
}

export interface SubmitResponse {
  id: string;
  status: ReviewStatus;
}

export type SSEStatusEvent = { event: 'status'; data: ReviewStatus };
export type SSEDoneEvent = { event: 'done'; data: Review };
export type SSEErrorEvent = { event: 'error'; data: string };
export type SSEEvent = SSEStatusEvent | SSEDoneEvent | SSEErrorEvent;
