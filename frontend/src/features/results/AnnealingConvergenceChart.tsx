import { useId, useState } from 'react'
import { Box, Paper, Stack, Typography } from '@mui/material'
import type { AnnealingHistory, AnnealingHistoryPoint } from '../../types'

const WIDTH = 400
const HEIGHT = 240
const LEFT = 58
const RIGHT = 16
const TOP = 24
const BOTTOM = 42
const PLOT_WIDTH = WIDTH - LEFT - RIGHT
const PLOT_HEIGHT = HEIGHT - TOP - BOTTOM
const CURRENT_COLOR = '#d97706'
const BEST_COLOR = '#2563eb'
const compactNumber = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 })
const lossNumber = new Intl.NumberFormat('en', { maximumFractionDigits: 2 })

export function AnnealingConvergenceChart({ history }: { history: AnnealingHistory }) {
  const titleId = useId()
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const { points } = history
  if (points.length === 0) return null

  const lastIndex = points.length - 1
  const selectedIndex = Math.min(activeIndex ?? lastIndex, lastIndex)
  const selected = points[selectedIndex]
  const lastIteration = points[lastIndex].iteration
  const losses = points.flatMap((point) => [point.current_loss, point.best_loss])
  const minimum = Math.min(...losses)
  const maximum = Math.max(...losses)
  const padding = (maximum - minimum || Math.abs(maximum) || 1) * 0.08
  const lower = minimum >= 0 ? Math.max(0, minimum - padding) : minimum - padding
  const upper = maximum + padding
  const x = (iteration: number) => LEFT + iteration / Math.max(lastIteration, 1) * PLOT_WIDTH
  const y = (loss: number) => TOP + (upper - loss) / (upper - lower) * PLOT_HEIGHT
  const line = (metric: 'current_loss' | 'best_loss') => points.map(
    (point) => `${x(point.iteration)},${y(point[metric])}`,
  ).join(' ')
  const xTicks = [...new Set([0, Math.round(lastIteration / 2), lastIteration])]
  const yTicks = Array.from({ length: 5 }, (_, index) => lower + (upper - lower) * index / 4)

  return (
    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
      <Stack spacing={0.5}>
        <Typography variant="subtitle2" fontWeight={700}>Loss over iterations</Typography>
        <Typography variant="caption" color="text.secondary">
          {history.run_count > 1
            ? `Winning run ${history.run_number} of ${history.run_count}`
            : 'Single run'}
          {' · '}{points.length} sampled points
        </Typography>
        <Stack direction="row" spacing={2} sx={{ pt: 0.5 }}>
          <Legend label="Current loss" color={CURRENT_COLOR} />
          <Legend label="Best loss" color={BEST_COLOR} />
        </Stack>
      </Stack>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-labelledby={titleId}
        tabIndex={0}
        style={{ display: 'block', width: '100%', color: '#64748b', cursor: 'crosshair' }}
        onPointerMove={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect()
          const position = (event.clientX - bounds.left) / bounds.width * WIDTH
          const iteration = (position - LEFT) / PLOT_WIDTH * lastIteration
          let nearest = 0
          points.forEach((point, index) => {
            if (Math.abs(point.iteration - iteration) < Math.abs(points[nearest].iteration - iteration)) {
              nearest = index
            }
          })
          setActiveIndex(nearest)
        }}
        onPointerLeave={() => setActiveIndex(null)}
        onBlur={() => setActiveIndex(null)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            event.preventDefault()
            const direction = event.key === 'ArrowLeft' ? -1 : 1
            setActiveIndex(Math.max(0, Math.min(lastIndex, selectedIndex + direction)))
          }
        }}
      >
        <title id={titleId}>
          Current and best loss versus iterations. Hover, or use left and right arrow keys, to inspect samples.
        </title>
        <text x={LEFT} y={13} fill="currentColor" fontSize={11}>Loss</text>
        {yTicks.map((value, index) => (
          <g key={index}>
            <line x1={LEFT} x2={WIDTH - RIGHT} y1={y(value)} y2={y(value)} stroke="#e2e8f0" />
            <text x={LEFT - 8} y={y(value)} dy="0.35em" textAnchor="end" fill="currentColor" fontSize={11}>
              {compactNumber.format(value)}
            </text>
          </g>
        ))}
        {xTicks.map((iteration) => (
          <text
            key={iteration}
            x={x(iteration)}
            y={HEIGHT - BOTTOM + 18}
            textAnchor="middle"
            fill="currentColor"
            fontSize={11}
          >
            {compactNumber.format(iteration)}
          </text>
        ))}
        <text x={LEFT + PLOT_WIDTH / 2} y={HEIGHT - 4} textAnchor="middle" fill="currentColor" fontSize={11}>
          Iterations
        </text>
        <polyline points={line('current_loss')} fill="none" stroke={CURRENT_COLOR} strokeWidth={1.75} />
        <polyline points={line('best_loss')} fill="none" stroke={BEST_COLOR} strokeWidth={2.5} />
        {activeIndex !== null && (
          <g pointerEvents="none">
            <line
              x1={x(selected.iteration)}
              x2={x(selected.iteration)}
              y1={TOP}
              y2={HEIGHT - BOTTOM}
              stroke="#94a3b8"
              strokeDasharray="3 3"
            />
            <circle cx={x(selected.iteration)} cy={y(selected.current_loss)} r={3.5} fill={CURRENT_COLOR} />
            <circle cx={x(selected.iteration)} cy={y(selected.best_loss)} r={3.5} fill={BEST_COLOR} />
          </g>
        )}
      </svg>

      <SampleValues point={selected} />
    </Paper>
  )
}

function Legend({ label, color }: { label: string; color: string }) {
  return (
    <Stack direction="row" alignItems="center" spacing={0.75}>
      <Box sx={{ width: 16, height: 3, borderRadius: 1, bgcolor: color }} />
      <Typography variant="caption" color="text.secondary">{label}</Typography>
    </Stack>
  )
}

function SampleValues({ point }: { point: AnnealingHistoryPoint }) {
  return (
    <Box sx={{ bgcolor: 'grey.50', borderRadius: 1, p: 1, fontVariantNumeric: 'tabular-nums' }}>
      <Typography variant="caption" color="text.secondary">
        Iteration {point.iteration.toLocaleString('en')}
      </Typography>
      <Stack direction="row" justifyContent="space-between" flexWrap="wrap" gap={0.5}>
        <Typography variant="caption" sx={{ color: CURRENT_COLOR }}>
          Current: {lossNumber.format(point.current_loss)}
        </Typography>
        <Typography variant="caption" sx={{ color: BEST_COLOR }}>
          Best: {lossNumber.format(point.best_loss)}
        </Typography>
      </Stack>
    </Box>
  )
}
