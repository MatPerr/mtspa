import { useState } from 'react'
import { Box, Stack, Tooltip, Typography } from '@mui/material'
import type { TimelineKind, TimelineSegment, TourTimeline as TourTimelineData } from '../../types'

const activities: Record<TimelineKind, { label: string; color: string; text: string }> = {
  travel: { label: 'Travel', color: '#2563eb', text: '#ffffff' },
  appointment: { label: 'Appointment', color: '#15803d', text: '#ffffff' },
  waiting: { label: 'Waiting', color: '#fbbf24', text: '#422006' },
  lateness: { label: 'Lateness', color: '#dc2626', text: '#ffffff' },
  overtime: { label: 'Overtime', color: '#7c3aed', text: '#ffffff' },
  available: { label: 'Available at home', color: '#f1f5f9', text: '#475569' },
}

export function formatClock(seconds: number): string {
  const days = Math.floor(seconds / 86_400)
  const hours = Math.floor(seconds % 86_400 / 3_600)
  const minutes = Math.floor(seconds % 3_600 / 60)
  const clock = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
  return days ? `${clock} (+${days}d)` : clock
}

function segmentLabel(segment: TimelineSegment): string {
  const appointment = segment.appointment_id === null ? 'Home' : `A${segment.appointment_id}`
  switch (segment.kind) {
    case 'appointment': return appointment
    case 'travel': return `Travel → ${appointment}`
    case 'waiting': return `Waiting for ${appointment}`
    case 'lateness': return `${appointment} lateness`
    default: return activities[segment.kind].label
  }
}

export function TourTimeline({ timeline }: { timeline: TourTimelineData }) {
  const [highlightedSegment, setHighlightedSegment] = useState<string | null>(null)
  const startTime = timeline.workday_start
  const endTime = timeline.end_time
  const span = endTime - startTime
  const position = (time: number) => (time - startTime) / span * 100
  const activity = timeline.segments.filter((segment) => !['lateness', 'overtime'].includes(segment.kind))
  const overtime = timeline.segments.filter((segment) => (
    segment.kind === 'overtime' && segment.end_time > segment.start_time
  ))
  const lateSegments = timeline.segments
    .filter((segment) => segment.kind === 'lateness' && segment.end_time > segment.start_time)
    .sort((a, b) => a.start_time - b.start_time)
  const latenessColumns: TimelineSegment[][] = []
  for (const segment of lateSegments) {
    const column = latenessColumns.find((segments) => segments.at(-1)!.end_time <= segment.start_time)
    if (column) column.push(segment)
    else latenessColumns.push([segment])
  }
  const tickStep = Math.max(1, Math.ceil(span / 3_600 / 10)) * 3_600
  const ticks = [startTime]
  for (let tick = Math.ceil(startTime / tickStep) * tickStep; tick < endTime; tick += tickStep) {
    // Leave enough space for the exact start/end labels when shifts begin between ticks.
    if (tick - startTime >= tickStep * 0.4 && endTime - tick >= tickStep * 0.4) ticks.push(tick)
  }
  ticks.push(endTime)
  const height = Math.max(480, Math.min(900, span / 3_600 * 60))
  const lanes = [
    { label: 'Activity', columns: [activity] },
    ...(lateSegments.length ? [{ label: 'Lateness', columns: latenessColumns }] : []),
    ...(overtime.length ? [{ label: 'Overtime', columns: [overtime] }] : []),
  ]
  const gridColumns = `60px minmax(100px, 2fr)${' minmax(56px, 1fr)'.repeat(lanes.length - 1)}`
  const legend = Object.entries(activities).filter(([kind]) => (
    (kind !== 'lateness' || lateSegments.length > 0) && (kind !== 'overtime' || overtime.length > 0)
  ))

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="subtitle1" fontWeight={700}>Workday timeline</Typography>
        <Typography variant="body2" color="text.secondary">
          Workday {formatClock(timeline.workday_start)}–{formatClock(timeline.workday_end)}
          {' · '}Home at {formatClock(timeline.return_time)}
        </Typography>
      </Box>

      <Stack direction="row" useFlexGap flexWrap="wrap" gap={1.5}>
        {legend.map(([kind, style]) => (
          <Stack key={kind} direction="row" spacing={0.75} alignItems="center">
            <Box sx={{ width: 12, height: 12, bgcolor: style.color, borderRadius: '3px', border: '1px solid #cbd5e1' }} />
            <Typography variant="caption">{style.label}</Typography>
          </Stack>
        ))}
      </Stack>

      <Box sx={{ display: 'grid', gridTemplateColumns: gridColumns, gap: 1 }}>
        <Typography variant="caption" color="text.secondary">Time</Typography>
        {lanes.map((lane) => (
          <Typography key={lane.label} variant="caption" fontWeight={700}>{lane.label}</Typography>
        ))}
        <Box sx={{ height, position: 'relative' }}>
          {ticks.map((tick, index) => (
            <Typography
              key={tick}
              variant="caption"
              color="text.secondary"
              sx={{
                position: 'absolute',
                top: `${position(tick)}%`,
                transform: index === 0 ? 'none' : index === ticks.length - 1 ? 'translateY(-100%)' : 'translateY(-50%)',
                fontSize: 11,
              }}
            >
              {tick === 86_400 ? '24:00' : formatClock(tick)}
            </Typography>
          ))}
        </Box>

        {lanes.map((lane) => (
          <Box
            key={lane.label}
            sx={{ height, position: 'relative', bgcolor: '#f8fafc', borderRadius: 1, border: '1px solid #e2e8f0' }}
          >
            {ticks.slice(1, -1).map((tick) => (
              <Box key={tick} sx={{
                position: 'absolute', insetInline: 0, top: `${position(tick)}%`,
                borderTop: '1px solid #e2e8f0', pointerEvents: 'none',
              }} />
            ))}
            {lane.columns.map((segments, columnIndex) => segments.map((segment, index) => {
              const style = activities[segment.kind]
              const duration = segment.end_time - segment.start_time
              const visibleStart = Math.max(startTime, segment.start_time)
              const visibleEnd = Math.min(endTime, segment.end_time)
              const visibleDuration = Math.max(0, visibleEnd - visibleStart)
              const thinDelay = (segment.kind === 'lateness' || segment.kind === 'overtime')
                && visibleDuration / span * height < 3
              const label = segmentLabel(segment)
              const durationLabel = duration < 60 ? `${duration} s` : `${(duration / 60).toFixed(1)} min`
              const description = `${label}: ${formatClock(segment.start_time)}–${formatClock(segment.end_time)}`
                + ` · ${durationLabel}`
              const segmentKey = `${lane.label}-${columnIndex}-${index}`
              return (
                <Tooltip key={segmentKey} title={description} arrow enterTouchDelay={0}>
                  <Box
                    component="span"
                    tabIndex={0}
                    role="img"
                    aria-label={description}
                    onMouseEnter={() => setHighlightedSegment(segmentKey)}
                    onMouseLeave={() => setHighlightedSegment(null)}
                    onFocus={() => setHighlightedSegment(segmentKey)}
                    onBlur={() => setHighlightedSegment(null)}
                    sx={{
                      position: 'absolute',
                      top: thinDelay
                        ? `min(${position(visibleStart)}%, calc(100% - 1px))`
                        : `${position(visibleStart)}%`,
                      height: `${visibleDuration / span * 100}%`,
                      left: `calc(${columnIndex / lane.columns.length * 100}% + 2px)`,
                      width: `calc(${100 / lane.columns.length}% - 4px)`,
                      minHeight: thinDelay ? '1px' : '2px',
                      zIndex: thinDelay ? 4 : duration === 0 ? 2 : 1,
                      bgcolor: style.color,
                      color: style.text,
                      opacity: highlightedSegment === null || highlightedSegment === segmentKey ? 1 : 0.35,
                      transition: 'opacity 120ms ease',
                      border: thinDelay ? 'none' : '1px solid #ffffff',
                      borderRadius: thinDelay ? 0 : '3px',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      overflow: 'hidden',
                      fontSize: 11,
                      fontWeight: 700,
                      cursor: 'default',
                      textAlign: 'center',
                      '&:focus-visible': { outline: '2px solid #0f172a', outlineOffset: 2, zIndex: 4 },
                    }}
                  >
                    {visibleDuration / span * height > 20 && (
                      <Box component="span" sx={{ maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {label}
                      </Box>
                    )}
                    {visibleDuration / span * height > 52 && (
                      <Box component="span" sx={{ fontWeight: 400, opacity: 0.9 }}>
                        {formatClock(segment.start_time)}–{formatClock(segment.end_time)}
                      </Box>
                    )}
                  </Box>
                </Tooltip>
              )
            }))}
            {[timeline.workday_start, timeline.workday_end].map((time, index) => (
              <Box key={index} sx={{
                position: 'absolute', insetInline: -3, top: `${position(time)}%`,
                borderTop: '1px dashed #475569', zIndex: 3, pointerEvents: 'none',
              }} />
            ))}
          </Box>
        ))}
      </Box>
    </Stack>
  )
}
