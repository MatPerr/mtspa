import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  ButtonBase,
  Chip,
  Collapse,
  Divider,
  Dialog,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material'
import type {
  LossConfigId,
  SolveResult,
  TourResult,
  TourMetrics,
} from '../../types'
import { TourTimeline } from './TourTimeline'

type ResultsPanelProps = {
  result: SolveResult
  selectedConfigId: LossConfigId | null
  selectedAgentId: number | null
  onSelectConfig: (configId: LossConfigId) => void
  onSelectAgent: (agentId: number | null) => void
}

const minutes = (seconds: number) => `${(seconds / 60).toFixed(1)} min`
const kilometers = (meters: number) => `${(meters / 1000).toFixed(2)} km`
const decimal = (value: number) => value.toFixed(2)

export function ResultsPanel({
  result,
  selectedConfigId,
  selectedAgentId,
  onSelectConfig,
  onSelectAgent,
}: ResultsPanelProps) {
  const solution = result.solutions.find(
    (candidate) => candidate.loss_config_id === selectedConfigId,
  ) ?? result.solutions[0]
  if (!solution) return null

  const metrics = solution.metrics
  return (
    <Stack spacing={1.75}>
      <Divider />
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">Result</Typography>
        <Chip label={result.solver.toUpperCase()} size="small" color="primary" />
      </Stack>

      {result.solutions.length > 1 ? (
        <Tabs
          value={solution.loss_config_id}
          variant="scrollable"
          scrollButtons="auto"
          onChange={(_, configId: LossConfigId) => onSelectConfig(configId)}
          sx={{
            minHeight: 40,
            borderBottom: 1,
            borderColor: 'divider',
            '& .MuiTab-root': {
              minHeight: 40,
              px: 1.5,
              textTransform: 'none',
            },
          }}
        >
          {result.solutions.map((candidate) => (
            <Tab
              key={candidate.loss_config_id}
              value={candidate.loss_config_id}
              label={candidate.loss_config_name}
            />
          ))}
        </Tabs>
      ) : (
        <Typography variant="subtitle2" color="text.secondary">
          {solution.loss_config_name}
        </Typography>
      )}

      <Box
        sx={{
          padding: 2,
          borderRadius: 2,
          color: 'primary.contrastText',
          backgroundColor: 'primary.main',
        }}
      >
        <Typography variant="overline" sx={{ opacity: 0.8 }}>
          Algorithm runtime
        </Typography>
        <Typography variant="h5" fontWeight={750}>
          {result.elapsed_seconds.toFixed(2)} s
        </Typography>
        {solution.final_state_count !== null && (
          <Typography variant="caption" sx={{ opacity: 0.8 }}>
            {solution.final_state_count.toLocaleString()} final DP states
          </Typography>
        )}
      </Box>

      {(metrics.total_lateness > 0 || metrics.total_overtime > 0) && (
        <Alert severity="warning">
          This solution includes lateness or overtime.
        </Alert>
      )}

      <MetricSection title="Totals">
        <Metric label="Total distance" value={kilometers(metrics.total_distance)} />
        <Metric label="Total travel time" value={minutes(metrics.total_travel_time)} />
        <Metric label="Total gain" value={metrics.total_gain.toLocaleString()} />
        <Metric label="Total gain/km" value={decimal(metrics.total_gain_per_km)} />
        <Metric label="Total gain/hour" value={decimal(metrics.total_gain_per_hour)} />
        <Metric label="Total lateness" value={minutes(metrics.total_lateness)} />
        <Metric label="Total waiting time" value={minutes(metrics.total_waiting_time)} />
        <Metric label="Total overtime" value={minutes(metrics.total_overtime)} />
      </MetricSection>

      <MetricSection title="Standard deviations">
        <Metric label="Distance std" value={kilometers(metrics.distance_std)} />
        <Metric label="Travel time std" value={minutes(metrics.travel_time_std)} />
        <Metric label="Gain std" value={decimal(metrics.gain_std)} />
        <Metric label="Gain/km std" value={decimal(metrics.gain_per_km_std)} />
        <Metric label="Gain/hour std" value={decimal(metrics.gain_per_hour_std)} />
        <Metric label="Waiting time std" value={minutes(metrics.waiting_time_std)} />
        <Metric label="Overtime std" value={minutes(metrics.overtime_std)} />
      </MetricSection>

      <Stack spacing={1}>
        <Typography variant="subtitle1" fontWeight={700}>Tours</Typography>
        {solution.tours.map((tour) => (
          <TourCard
            key={`${solution.loss_config_id}-${tour.agent_id}`}
            tour={tour}
            expanded={selectedAgentId === tour.agent_id}
            onToggle={() => onSelectAgent(
              selectedAgentId === tour.agent_id ? null : tour.agent_id,
            )}
          />
        ))}
      </Stack>
    </Stack>
  )
}

function MetricSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>
      <Box className="metric-grid">{children}</Box>
    </Stack>
  )
}

function TourCard({
  tour,
  expanded,
  onToggle,
}: {
  tour: TourResult
  expanded: boolean
  onToggle: () => void
}) {
  const [timelineOpen, setTimelineOpen] = useState(false)
  const route = [
    'Home',
    ...tour.appointment_ids.map((appointmentId) => `A${appointmentId}`),
    'Home',
  ].join(' → ')
  return (
    <Paper
      variant="outlined"
      sx={{
        overflow: 'hidden',
        borderColor: expanded ? 'primary.main' : 'divider',
      }}
    >
      <ButtonBase
        aria-expanded={expanded}
        onClick={onToggle}
        sx={{ display: 'block', width: '100%', padding: 1.25, textAlign: 'left' }}
      >
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Box minWidth={0}>
            <Typography variant="body2" fontWeight={700}>{tour.agent_name}</Typography>
            <Typography variant="caption" color="text.secondary">
              {tour.appointment_ids.length} appointment
              {tour.appointment_ids.length === 1 ? '' : 's'} · {route}
            </Typography>
          </Box>
        </Stack>
      </ButtonBase>
      <Collapse in={expanded} unmountOnExit>
        <Box sx={{ padding: 1.25, paddingTop: 0 }}>
          <Divider sx={{ marginBottom: 1.25 }} />
          <Button
            variant="outlined"
            size="small"
            aria-haspopup="dialog"
            onClick={() => setTimelineOpen(true)}
            sx={{ mb: 1.5 }}
            startIcon={(
              <Box component="svg" viewBox="0 0 20 20" aria-hidden="true" sx={{ width: 18, height: 18 }}>
                <path d="M3 4v12h14M5 7h5m2 0h4M5 11h3m2 0h6" fill="none" stroke="currentColor" strokeWidth="2" />
              </Box>
            )}
          >
            Timeline
          </Button>
          <TourMetricGrid metrics={tour.metrics} />
        </Box>
      </Collapse>
      <Dialog
        open={expanded && timelineOpen}
        onClose={() => setTimelineOpen(false)}
        maxWidth="lg"
        fullWidth
        aria-labelledby={`tour-timeline-title-${tour.agent_id}`}
        slotProps={{ paper: { sx: { m: { xs: 1, sm: 3 }, width: { xs: 'calc(100% - 16px)', sm: '100%' } } } }}
      >
        <DialogTitle id={`tour-timeline-title-${tour.agent_id}`} component="div">
          <Stack direction="row" justifyContent="space-between" alignItems="center" gap={2}>
            <Box>
              <Typography variant="h6" component="h2">{tour.agent_name} · Timeline</Typography>
              <Typography variant="body2" color="text.secondary">{route}</Typography>
            </Box>
            <Button onClick={() => setTimelineOpen(false)} sx={{ flexShrink: 0 }}>Close</Button>
          </Stack>
        </DialogTitle>
        <DialogContent dividers>
          <Box sx={{
            display: 'grid',
            gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'minmax(0, 1fr) 170px' },
            gap: 3,
          }}>
            <Box sx={{ minWidth: 0 }}><TourTimeline timeline={tour.timeline} /></Box>
            <Box sx={{
              position: { md: 'sticky' },
              top: 0,
              alignSelf: 'start',
              borderLeft: { md: '1px solid' },
              borderTop: { xs: '1px solid', md: 0 },
              borderColor: 'divider',
              pl: { md: 3 },
              pt: { xs: 2, md: 0 },
            }}>
              <Typography variant="subtitle2" sx={{ mb: 1.5 }}>Tour metrics</Typography>
              <TourMetricGrid metrics={tour.metrics} singleColumn />
            </Box>
          </Box>
        </DialogContent>
      </Dialog>
    </Paper>
  )
}

function TourMetricGrid({ metrics, singleColumn = false }: { metrics: TourMetrics; singleColumn?: boolean }) {
  return (
    <Box className="metric-grid" sx={singleColumn ? { gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: '1fr' } } : {}}>
      <Metric label="Distance" value={kilometers(metrics.distance)} />
      <Metric label="Travel time" value={minutes(metrics.travel_time)} />
      <Metric label="Elapsed time" value={minutes(metrics.elapsed_time)} />
      <Metric label="Gain" value={metrics.gain.toLocaleString()} />
      <Metric label="Gain/km" value={decimal(metrics.gain_per_km)} />
      <Metric label="Gain/hour" value={decimal(metrics.gain_per_hour)} />
      <Metric label="Lateness" value={minutes(metrics.lateness)} />
      <Metric label="Waiting time" value={minutes(metrics.waiting_time)} />
      <Metric label="Overtime" value={minutes(metrics.overtime)} />
    </Box>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="body2" fontWeight={750}>{value}</Typography>
    </Box>
  )
}
