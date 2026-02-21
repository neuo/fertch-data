export interface Bar {
  date: string
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  RSI_14: number | null
  EMA_10: number | null
  EMA_20: number | null
}

export interface ApiDataResponse {
  ticker: string
  bars: Bar[]
}

export type RangeKey = '1D' | '3D'
