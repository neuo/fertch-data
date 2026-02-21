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

function toTimestamp(date: string, time: string): UTCTimestamp {
  return Math.floor(new Date(`${date}T${time}:00-05:00`).getTime() / 1000) as UTCTimestamp
}

const CHART_BG = '#0f0f14'
const GRID_COLOR = '#1e1e2e'
const TEXT_COLOR = '#9598a1'
const BORDER_COLOR = '#2a2a3e'

export default function Chart({ bars }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
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

  return <div ref={containerRef} className="w-full h-full" />
}
