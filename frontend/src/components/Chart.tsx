import { useEffect, useRef } from 'react'
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  ColorType,
  LineStyle,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Bar } from '../types'

interface ChartProps {
  bars: Bar[]
}

function fmt(n: number) {
  return n.toFixed(2)
}
function fmtVol(n: number) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

// Use Z so the chart treats HH:MM as-is (no tz conversion).
// The records already store ET times (09:30 = market open).
function toTimestamp(date: string, time: string): UTCTimestamp {
  return Math.floor(new Date(`${date}T${time}:00Z`).getTime() / 1000) as UTCTimestamp
}

const CHART_BG = '#0f0f14'
const GRID_COLOR = '#1e1e2e'
const TEXT_COLOR = '#9598a1'
const BORDER_COLOR = '#2a2a3e'

export default function Chart({ bars }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_BG },
        textColor: TEXT_COLOR,
      },
      grid: {
        vertLines: { color: GRID_COLOR },
        horzLines: { color: GRID_COLOR },
      },
      crosshair: { vertLine: { labelBackgroundColor: '#2a2a3e' }, horzLine: { labelBackgroundColor: '#2a2a3e' } },
      rightPriceScale: { borderColor: BORDER_COLOR },
      timeScale: {
        borderColor: BORDER_COLOR,
        timeVisible: true,
        secondsVisible: false,
      },
      localization: {
        timeFormatter: (ts: number) => {
          const d = new Date(ts * 1000)
          const YYYY = d.getUTCFullYear()
          const MM = String(d.getUTCMonth() + 1).padStart(2, '0')
          const DD = String(d.getUTCDate()).padStart(2, '0')
          const hh = String(d.getUTCHours()).padStart(2, '0')
          const mm = String(d.getUTCMinutes()).padStart(2, '0')
          return `${YYYY}-${MM}-${DD} ${hh}:${mm}`
        },
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    })

    chartRef.current = chart

    // --- RSI pane (second pane) ---
    const rsiPane = chart.addPane()

    // --- Price series (main pane) ---
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })

    const vwapSeries = chart.addSeries(LineSeries, {
      color: '#a855f7',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: 'VWAP',
      priceLineVisible: false,
      lastValueVisible: false,
    })

    // --- RSI series (second pane) ---
    const rsiSeries = rsiPane.addSeries(LineSeries, {
      color: '#facc15',
      lineWidth: 1,
      title: 'RSI(14)',
      priceScaleId: 'rsi',
    })

    // Overbought / Oversold reference lines
    rsiPane.addSeries(LineSeries, {
      color: '#ef535066',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceScaleId: 'rsi',
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    }).setData(bars.length ? [
      { time: toTimestamp(bars[0].date, bars[0].time), value: 70 },
      { time: toTimestamp(bars[bars.length - 1].date, bars[bars.length - 1].time), value: 70 },
    ] : [])

    rsiPane.addSeries(LineSeries, {
      color: '#26a69a66',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceScaleId: 'rsi',
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    }).setData(bars.length ? [
      { time: toTimestamp(bars[0].date, bars[0].time), value: 30 },
      { time: toTimestamp(bars[bars.length - 1].date, bars[bars.length - 1].time), value: 30 },
    ] : [])

    // --- Populate data ---
    type OHLC = { time: UTCTimestamp; open: number; high: number; low: number; close: number }
    type Point = { time: UTCTimestamp; value: number }
    // whitespace breaks the VWAP line between trading days
    type VWAPPoint = { time: UTCTimestamp } | Point

    const candleData: OHLC[] = []
    const vwapData: VWAPPoint[] = []
    const rsiData: Point[] = []

    let cumTPV = 0
    let cumVol = 0
    let prevDate = ''
    let prevTs: UTCTimestamp | null = null

    for (const bar of bars) {
      const ts = toTimestamp(bar.date, bar.time)
      candleData.push({ time: ts, open: bar.open, high: bar.high, low: bar.low, close: bar.close })
      if (bar.RSI_14 != null) rsiData.push({ time: ts, value: bar.RSI_14 })

      if (bar.date !== prevDate) {
        // Insert whitespace to break VWAP line at day boundary
        if (prevTs !== null) vwapData.push({ time: (prevTs + 1) as UTCTimestamp })
        cumTPV = 0
        cumVol = 0
        prevDate = bar.date
      }
      const tp = (bar.high + bar.low + bar.close) / 3
      cumTPV += tp * bar.volume
      cumVol += bar.volume
      if (cumVol > 0) vwapData.push({ time: ts, value: cumTPV / cumVol })
      prevTs = ts
    }

    candleSeries.setData(candleData)
    vwapSeries.setData(vwapData)
    rsiSeries.setData(rsiData)

    // Build ts → bar lookup for tooltip
    const barMap = new Map<number, Bar>()
    for (const bar of bars) {
      barMap.set(toTimestamp(bar.date, bar.time), bar)
    }

    chart.subscribeCrosshairMove((param) => {
      const el = tooltipRef.current
      if (!el) return
      if (!param.time || !param.seriesData.size) {
        el.style.display = 'none'
        return
      }
      const bar = barMap.get(param.time as number)
      if (!bar) { el.style.display = 'none'; return }

      const change = bar.close - bar.open
      const changePct = (change / bar.open) * 100
      const color = change >= 0 ? '#26a69a' : '#ef5350'

      el.style.display = 'block'
      el.innerHTML = `
        <span style="color:#9598a1">${bar.date} ${bar.time}</span>
        <span style="margin-left:8px;color:${color};font-weight:600">${change >= 0 ? '+' : ''}${fmt(change)} (${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%)</span>
        <span style="margin-left:12px">O <b>${fmt(bar.open)}</b></span>
        <span style="margin-left:8px">H <b style="color:#26a69a">${fmt(bar.high)}</b></span>
        <span style="margin-left:8px">L <b style="color:#ef5350">${fmt(bar.low)}</b></span>
        <span style="margin-left:8px">C <b>${fmt(bar.close)}</b></span>
        <span style="margin-left:8px;color:#9598a1">Vol <b style="color:#d1d4dc">${fmtVol(bar.volume)}</b></span>
      `
    })

    chart.timeScale().fitContent()

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        })
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [bars])

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full" />
      <div
        ref={tooltipRef}
        style={{ display: 'none' }}
        className="absolute top-2 left-2 z-10 px-3 py-1.5 rounded text-xs bg-[#1a1a2e]/90 border border-[#2a2a3e] pointer-events-none whitespace-nowrap"
      />
    </div>
  )
}
