import { useQuery } from "@tanstack/react-query";
import { getStats, listReviews } from "@/lib/api";
import { Button } from "@/components/ui/button";
import ReviewCard from "@/components/ReviewCard";
import { useMemo, useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HistoryFilters, type HistoryFilterValue } from "@/components/HistoryFilters";
import { endOfDay } from "date-fns";
import type { Review, StatsResponse, GetStatsParams, ListReviewsParams, PaginatedReviewsResponse } from "@/lib/types";

const DEFAULT_FILTERS: HistoryFilterValue = {
  language: "all",
  scoreRange: [0, 10],
  date: undefined,
};

function toReviewParams(f: HistoryFilterValue, page: number = 1): ListReviewsParams {
  const params: ListReviewsParams = { page, page_size: 20 };
  if (f.language && f.language !== "all") params.language = f.language;
  const [min, max] = f.scoreRange ?? [0, 10];
  if (min > 0) params.min_score = min;
  if (max < 10) params.max_score = max;
  if (f.date?.from) params.start_date = f.date.from.toISOString();
  if (f.date?.to) params.end_date = endOfDay(f.date.to).toISOString();
  return params;
}

function toStatsParams(f: HistoryFilterValue): GetStatsParams {
  const params: GetStatsParams = {};
  if (f.language && f.language !== "all") params.language = f.language;
  if (f.date?.from) params.start_date = f.date.from.toISOString();
  if (f.date?.to) params.end_date = endOfDay(f.date.to).toISOString();
  return params;
}

type CsvRow = {
  id: string;
  language: string;
  status: Review["status"];
  score: number | "";
  created_at: string;
};

export default function History() {
  const [filters, setFilters] = useState<HistoryFilterValue>(DEFAULT_FILTERS);
  const [applied, setApplied] = useState<HistoryFilterValue>(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);

  // Debounce filter updates (500ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setApplied(filters);
      setPage(1); // Reset to first page when filters change
    }, 500);
    return () => clearTimeout(timer);
  }, [filters]);

  const reviewParams = useMemo(() => toReviewParams(applied, page), [applied, page]);
  const statsParams = useMemo(() => toStatsParams(applied), [applied]);

  const reviewsQ = useQuery<PaginatedReviewsResponse, Error>({
    queryKey: ["reviews", reviewParams],
    queryFn: () => listReviews(reviewParams),
  });

  const statsQ = useQuery<StatsResponse, Error>({
    queryKey: ["stats", statsParams],
    queryFn: () => getStats(statsParams),
  });

  const items = reviewsQ.data?.items ?? [];
  const total = reviewsQ.data?.total ?? 0;
  const pageSize = reviewsQ.data?.page_size ?? 20;
  const totalPages = Math.ceil(total / pageSize);

  function onApply() {
    setApplied(filters);
    setPage(1);
  }

  function onReset() {
    setFilters(DEFAULT_FILTERS);
    setApplied(DEFAULT_FILTERS);
    setPage(1);
  }

  function exportCSV() {
    // Export all items from current page (could be extended to export all)
    const rows: CsvRow[] = items.map((r) => ({
      id: r.id,
      language: r.language,
      status: r.status,
      score: r.score ?? "",
      created_at: r.created_at,
    }));

    const headers = ["id", "language", "status", "score", "created_at"] as const;
    const csv = [
      headers.join(","),
      ...rows.map((r) => headers.map((h) => JSON.stringify(r[h] ?? "")).join(",")),
    ].join("\n");

    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "reviews.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="grid-gap w-full px-5">
      <div className="flex flex-col gap-3">
        <HistoryFilters value={filters} onChange={setFilters} onApply={onApply} onReset={onReset} />
        <div className="flex gap-2">
          <Button variant="secondary" onClick={exportCSV}>Export CSV</Button>
        </div>
      </div>

      <div className="md:flex justify-center gap-3">
        <div className="grid-gap flex-1">
          {reviewsQ.isLoading && <div>Loading...</div>}
          {reviewsQ.error && <div className="text-rose-300">{reviewsQ.error.message}</div>}
          {items.map((r) => <ReviewCard marginTop={2} key={r.id} review={r} />)}
          {!reviewsQ.isLoading && items.length === 0 && (
            <div className="text-sm text-muted-foreground">No results.</div>
          )}
          
          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <div className="text-sm text-muted-foreground">
                Showing {((page - 1) * pageSize) + 1} to {Math.min(page * pageSize, total)} of {total} reviews
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1 || reviewsQ.isLoading}
                >
                  Previous
                </Button>
                <div className="flex items-center gap-1 text-sm">
                  <span>Page</span>
                  <span className="font-medium">{page}</span>
                  <span>of</span>
                  <span className="font-medium">{totalPages}</span>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages || reviewsQ.isLoading}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </div>

        <Card className="h-max w-max min-w-60 mt-2">
          <CardHeader>
            <CardTitle>Stats</CardTitle>
          </CardHeader>
          <CardContent>
            {statsQ.isLoading && <div>Loading...</div>}
            {statsQ.error && <div className="text-rose-300">{statsQ.error.message}</div>}
            {statsQ.data && (
              <div className="grid gap-2 text-sm">
                <div><b>Total reviews:</b> {statsQ.data.total}</div>
                <div><b>Average score:</b> {statsQ.data.avg_score ?? "—"}</div>
                <div>
                  <b>Common issues:</b>
                  <ul className="list-disc pl-5 mt-2">
                    {statsQ.data.common_issues.slice(0, 10).map((t, i) => <li key={i}>{t}</li>)}
                  </ul>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
