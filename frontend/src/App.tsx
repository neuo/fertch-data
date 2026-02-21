import { useEffect, useState, useCallback } from 'react'
import { fetchTickers, fetchData, triggerUpdate, fetchUpdateStatus, lastTradingDayStr, todayStr } from './api'
import Chart from './components/Chart'
import type { Bar, RangeKey } from './types'

const RANGE_OPTIONS: RangeKey[] = ['1D', '3D']

export default function App() {
  const [tickers, setTickers] = useState<string[]>([])
  const [activeTicker, setActiveTicker] = useState<string>('')
  const [activeRange, setActiveRange] = useState<RangeKey>('1D')
  const [startDate, setStartDate] = useState<string>(lastTradingDayStr())
  const [bars, setBars] = useState<Bar[]>([])
  const [loading, setLoading] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [lastRun, setLastRun] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTickers()
      .then((t) => {
        setTickers(t)
        if (t.length) setActiveTicker(t[0])
      })
      .catch(() => setError('Backend not reachable — is the API server running?'))
  }, [])

  const loadData = useCallback(async () => {
    if (!activeTicker) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetchData(activeTicker, startDate, activeRange)
      setBars(res.bars)
    } catch {
      setError('Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [activeTicker, startDate, activeRange])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleUpdate = async () => {
    setUpdating(true)
    try {
      await triggerUpdate([activeTicker])
      // Poll until done
      const poll = setInterval(async () => {
        const status = await fetchUpdateStatus()
        if (!status.running) {
          clearInterval(poll)
          setUpdating(false)
          setLastRun(status.last_run)
          loadData()
        }
      }, 2000)
    } catch {
      setUpdating(false)
      setError('Update failed')
    }
  }

  const priceChange =
    bars.length >= 2
      ? ((bars[bars.length - 1].close - bars[0].open) / bars[0].open) * 100
      : null

  return (
    <div className="flex flex-col h-screen bg-[#0f0f14] text-[#d1d4dc]">
      {/* Toolbar */}
      <header className="flex items-center gap-3 px-4 py-2 border-b border-[#1e1e2e] shrink-0">
        <span className="font-bold text-white tracking-wide text-sm mr-2">FinData</span>

        {/* Ticker selector */}
        <div className="flex gap-1">
          {tickers.map((t) => (
            <button
              key={t}
              onClick={() => setActiveTicker(t)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                activeTicker === t
                  ? 'bg-blue-600 text-white'
                  : 'text-[#9598a1] hover:text-white hover:bg-[#1e1e2e]'
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="w-px h-5 bg-[#2a2a3e] mx-1" />

        {/* Date picker */}
        <input
          type="date"
          value={startDate}
          max={todayStr()}
          onChange={(e) => e.target.value && setStartDate(e.target.value)}
          className="bg-[#1e1e2e] border border-[#2a2a3e] text-[#d1d4dc] text-xs rounded px-2 py-1 focus:outline-none focus:border-blue-500 transition-colors [color-scheme:dark]"
        />

        {/* Range selector */}
        <div className="flex gap-1">
          {RANGE_OPTIONS.map((r) => (
            <button
              key={r}
              onClick={() => setActiveRange(r)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                activeRange === r
                  ? 'bg-[#2a2a3e] text-white'
                  : 'text-[#9598a1] hover:text-white hover:bg-[#1a1a2e]'
              }`}
            >
              {r}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        {/* Price change badge */}
        {priceChange != null && (
          <span
            className={`text-xs font-semibold px-2 py-0.5 rounded ${
              priceChange >= 0 ? 'text-[#26a69a] bg-[#26a69a1a]' : 'text-[#ef5350] bg-[#ef53501a]'
            }`}
          >
            {priceChange >= 0 ? '+' : ''}
            {priceChange.toFixed(2)}%
          </span>
        )}

        {lastRun && (
          <span className="text-[10px] text-[#555]">
            Updated {new Date(lastRun).toLocaleTimeString()}
          </span>
        )}

        {/* Update button */}
        <button
          onClick={handleUpdate}
          disabled={updating || loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-[#1e1e2e] border border-[#2a2a3e] text-xs text-[#9598a1] hover:text-white hover:border-blue-500 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <svg
            className={`w-3.5 h-3.5 ${updating ? 'animate-spin' : ''}`}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path d="M21 12a9 9 0 11-6.219-8.56" strokeLinecap="round" />
          </svg>
          {updating ? 'Updating…' : 'Update'}
        </button>
      </header>

      {/* Indicator legend */}
      <div className="flex items-center gap-4 px-4 py-1 text-[10px] text-[#555] border-b border-[#1e1e2e] shrink-0">
        <span className="flex items-center gap-1">
          <span className="w-3 h-0.5 bg-[#a855f7] inline-block" /> VWAP
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-0.5 bg-[#facc15] inline-block" /> RSI(14)
        </span>
      </div>

      {/* Chart area */}
      <div className="flex-1 relative min-h-0">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10 bg-[#0f0f14]/70">
            <span className="text-sm text-[#555]">Loading…</span>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <span className="text-sm text-[#ef5350]">{error}</span>
          </div>
        )}
        {!loading && !error && bars.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-sm text-[#555]">No data for this range</span>
          </div>
        )}
        {bars.length > 0 && <Chart bars={bars} />}
      </div>
    </div>
  )
}
