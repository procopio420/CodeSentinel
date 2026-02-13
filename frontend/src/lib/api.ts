import { getJSON, postJSON } from './http';
import type { GetStatsParams, ListReviewsParams, PaginatedReviewsResponse, Review, StatsResponse, SubmitPayload, SubmitResponse } from './types';

const BASE = import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8000';

function buildQueryParams(params: Record<string, string | number | undefined>): string {
  const url = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value !== undefined) url.set(key, String(value));
  const stringParams = url.toString();
  return stringParams ? `?${stringParams}` : '';
}

export function getReview(id: string): Promise<Review> {
  return getJSON<Review>(`${BASE}/api/reviews/${id}`);
}

export function listReviews(params: ListReviewsParams): Promise<PaginatedReviewsResponse> {
  return getJSON<PaginatedReviewsResponse>(`${BASE}/api/reviews${buildQueryParams({ ...params })}`);
}

export function getStats(params: GetStatsParams): Promise<StatsResponse> {
  return getJSON<StatsResponse>(`${BASE}/api/stats${buildQueryParams({ ...params })}`);
}

export function submitReview(payload: SubmitPayload): Promise<SubmitResponse> {
  return postJSON<SubmitResponse, SubmitPayload>(`${BASE}/api/reviews`, payload);
}
