import { useState, useEffect, useCallback } from 'react';
import type { BlueprintData, BlueprintSummary } from '../types';

const POLL_INTERVAL = 5000;

export function useBlueprintData() {
  const [data, setData] = useState<BlueprintData | null>(null);
  const [summary, setSummary] = useState<BlueprintSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [bpRes, sumRes] = await Promise.all([
        fetch('/api/blueprint'),
        fetch('/api/summary'),
      ]);
      if (!bpRes.ok || !sumRes.ok) throw new Error('API error');
      const bp = await bpRes.json();
      const sum = await sumRes.json();
      setData(bp);
      setSummary(sum);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchData]);

  return { data, summary, loading, error, refetch: fetchData };
}
