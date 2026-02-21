import type { ApiDataResponse, RangeKey } from './types'

export function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr + 'T00:00:00')
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

export function lastTradingDayStr(): string {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  while (d.getDay() === 0 || d.getDay() === 6) {
    d.setDate(d.getDate() - 1)
  }
  return d.toISOString().slice(0, 10)
}

export function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

export async function fetchTickers(): Promise<string[]> {
  const res = await fetch('/api/tickers')
  if (!res.ok) throw new Error('Failed to fetch tickers')
  return res.json()
}

export async function fetchData(
  ticker: string,
  start: string,
  range: RangeKey,
): Promise<ApiDataResponse> {
  const days: Record<RangeKey, number> = { '1D': 1, '3D': 3 }
  const end = addDays(start, days[range])
  const res = await fetch(`/api/data/${ticker}?start=${start}&end=${end}`)
  if (!res.ok) throw new Error(`Failed to fetch data for ${ticker}`)
  return res.json()
}

export async function triggerUpdate(tickers: string[]): Promise<{ status: string }> {
  const res = await fetch('/api/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tickers }),
  })
  if (!res.ok) throw new Error('Failed to trigger update')
  return res.json()
}

export async function fetchUpdateStatus(): Promise<{
  running: boolean
  last_run: string | null
  error: string | null
}> {
  const res = await fetch('/api/update/status')
  if (!res.ok) throw new Error('Failed to fetch status')
  return res.json()
}
