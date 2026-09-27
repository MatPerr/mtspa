import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Collapse,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import type {
  AgentDraft,
  AppointmentDraft,
  Coordinate,
  DataSource,
  LossConfig,
  LossConfigId,
  OptimizationProgress,
  PlacementMode,
  SampleDataset,
  SolveOptions,
  SolveResult,
  SolverName,
} from '../../types'
import { ResultsPanel } from '../results/ResultsPanel'
import { AgentForm } from './AgentForm'
import { AppointmentForm } from './AppointmentForm'

type ProblemSidebarProps = {
  agents: AgentDraft[]
  appointments: AppointmentDraft[]
  dataSource: DataSource
  selectedSampleId: string
  placementMode: PlacementMode
  pickedLocation: Coordinate | null
  loading: boolean
  optimizationProgress: OptimizationProgress | null
  sampleLoading: boolean
  sampleDatasets: SampleDataset[]
  error: string | null
  warning: string | null
  lossConfigs: LossConfig[]
  result: SolveResult | null
  selectedConfigId: LossConfigId | null
  selectedAgentId: number | null
  onDataSourceChange: (source: DataSource) => void
  onPlacementModeChange: (mode: PlacementMode) => void
  onAddAgent: (agent: Omit<AgentDraft, 'id'>) => void
  onAddAppointment: (appointment: Omit<AppointmentDraft, 'id'>) => void
  onLoadSample: (sampleId: string) => void
  onDeleteAgent: (id: string) => void
  onDeleteAppointment: (id: string) => void
  onSolve: (options: SolveOptions) => void
  onSelectConfig: (configId: LossConfigId) => void
  onSelectAgent: (agentId: number | null) => void
}

export function ProblemSidebar(props: ProblemSidebarProps) {
  const [solver, setSolver] = useState<SolverName>('sa')
  const [stepsInput, setStepsInput] = useState('50000')
  const [runsInput, setRunsInput] = useState('1')
  const [seedInput, setSeedInput] = useState('0')
  const [lossConfigIds, setLossConfigIds] = useState<LossConfigId[]>([
    'shortest_distance',
  ])
  const [dpLossConfigIds, setDpLossConfigIds] = useState<LossConfigId[]>([
    'shortest_distance',
  ])
  const [nodesExpanded, setNodesExpanded] = useState(false)
  const saLossConfigs = props.lossConfigs.filter(
    (config) => config.supported_solvers.includes('sa'),
  )
  const dpLossConfigs = props.lossConfigs.filter(
    (config) => config.supported_solvers.includes('dp'),
  )
  const selectedLossConfigIds = solver === 'sa'
    ? lossConfigIds
    : dpLossConfigIds
  const availableLossConfigs = solver === 'sa'
    ? saLossConfigs
    : dpLossConfigs
  const steps = parseInteger(stepsInput)
  const runs = parseInteger(runsInput)
  const seed = parseInteger(seedInput)
  const stepsValid = steps !== undefined && steps > 0
  const runsValid = runs !== undefined && runs > 0
  const seedValid = seedInput.trim() === '' || seed !== undefined
  const canSolve =
    props.agents.length > 0 &&
    props.appointments.length > 0 &&
    availableLossConfigs.length > 0 &&
    selectedLossConfigIds.length > 0 &&
    (solver === 'dp' || (props.agents.length >= 2 && stepsValid && runsValid && seedValid))
  const progressPercent = props.optimizationProgress
    ? Math.floor(
        Math.min(1, props.optimizationProgress.current / props.optimizationProgress.total) * 100,
      )
    : 0
  const showProgress = props.loading && props.optimizationProgress !== null
  const progressLabel = props.optimizationProgress?.metric === 'states'
    ? `DP memory · ${formatStateCount(props.optimizationProgress.current)} / ${formatStateCount(props.optimizationProgress.total)} states`
    : `Optimizing… ${progressPercent}%`

  return (
    <Paper square elevation={3} className="sidebar">
      <Stack spacing={2.25}>
        <ToggleButtonGroup
          aria-label="Data source"
          value={props.dataSource}
          exclusive
          fullWidth
          size="small"
          disabled={props.sampleLoading || props.loading}
          onChange={(_, value: DataSource | null) => {
            if (value && value !== props.dataSource) props.onDataSourceChange(value)
          }}
        >
          <ToggleButton value="sample">Sample data</ToggleButton>
          <ToggleButton value="manual">Manual data</ToggleButton>
        </ToggleButtonGroup>

        {props.dataSource === 'sample' ? (
          <TextField
            select
            label={props.sampleLoading ? 'Loading sample…' : 'Sample dataset'}
            value={props.selectedSampleId}
            onChange={(event) => props.onLoadSample(event.target.value)}
            disabled={props.sampleLoading || props.loading || props.sampleDatasets.length === 0}
            fullWidth
            size="small"
          >
            {props.sampleDatasets.map((sample) => (
              <MenuItem key={sample.id} value={sample.id}>
                {sample.name}
              </MenuItem>
            ))}
          </TextField>
        ) : (
          <Stack component="fieldset" disabled={props.loading} spacing={2} sx={{ border: 0, p: 0, m: 0, minWidth: 0 }}>
            <ToggleButtonGroup
              value={props.placementMode}
              exclusive
              fullWidth
              size="small"
              disabled={props.loading}
              onChange={(_, value: PlacementMode | null) => value && props.onPlacementModeChange(value)}
            >
              <ToggleButton value="agent">Add agent</ToggleButton>
              <ToggleButton value="appointment">Add appointment</ToggleButton>
            </ToggleButtonGroup>
            {props.placementMode === 'agent' ? (
              <AgentForm
                pickedLocation={props.pickedLocation}
                nextAgentNumber={props.agents.length + 1}
                onAdd={props.onAddAgent}
              />
            ) : (
              <AppointmentForm pickedLocation={props.pickedLocation} onAdd={props.onAddAppointment} />
            )}
          </Stack>
        )}

        <Divider />
        <Button
          color="inherit"
          fullWidth
          aria-controls="nodes-section"
          aria-expanded={nodesExpanded}
          onClick={() => setNodesExpanded((expanded) => !expanded)}
          sx={{
            justifyContent: 'space-between',
            minHeight: 48,
            px: 1.5,
            py: 1,
            borderRadius: 2,
            bgcolor: 'action.hover',
            textTransform: 'none',
            '&:hover': { bgcolor: 'action.selected' },
          }}
        >
          <Typography component="span" variant="h6">Nodes</Typography>
          <Box
            component="span"
            aria-hidden
            sx={{
              width: 9,
              height: 9,
              mr: 0.5,
              borderRight: 2,
              borderBottom: 2,
              borderColor: 'currentColor',
              transform: nodesExpanded ? 'rotate(225deg)' : 'rotate(45deg)',
              transition: 'transform 150ms ease',
            }}
          />
        </Button>
        <Collapse in={nodesExpanded} unmountOnExit>
          <Box id="nodes-section">
            <DraftList
              agents={props.agents}
              appointments={props.appointments}
              readOnly={props.dataSource === 'sample' || props.loading}
              onDeleteAgent={props.onDeleteAgent}
              onDeleteAppointment={props.onDeleteAppointment}
            />
          </Box>
        </Collapse>

        <Divider />
        <Typography variant="h6">Optimization</Typography>
        <FormControl size="small" fullWidth>
          <InputLabel id="solver-label">Solver</InputLabel>
          <Select
            labelId="solver-label"
            label="Solver"
            value={solver}
            onChange={(event) => setSolver(event.target.value as SolverName)}
          >
            <MenuItem value="sa">Simulated annealing (approximate)</MenuItem>
            <MenuItem value="dp">Dynamic programming (exact)</MenuItem>
          </Select>
        </FormControl>
        {solver === 'sa' && (
          <Stack spacing={1.5}>
            <LossConfigSelect
              id="sa-loss-configs"
              configs={saLossConfigs}
              selected={lossConfigIds}
              onChange={setLossConfigIds}
            />
            <Stack direction="row" spacing={1}>
              <TextField
                label="Steps"
                value={stepsInput}
                onChange={(event) => setStepsInput(event.target.value)}
                error={stepsInput.trim() !== '' && !stepsValid}
                helperText={stepsInput.trim() !== '' && !stepsValid ? 'Enter a positive whole number.' : undefined}
                size="small"
                slotProps={{ htmlInput: { inputMode: 'numeric' } }}
                fullWidth
              />
              <TextField
                label="Runs"
                value={runsInput}
                onChange={(event) => setRunsInput(event.target.value)}
                error={runsInput.trim() !== '' && !runsValid}
                helperText={runsInput.trim() !== '' && !runsValid ? 'Enter a positive whole number.' : undefined}
                size="small"
                slotProps={{ htmlInput: { inputMode: 'numeric' } }}
                fullWidth
              />
              <TextField
                label="Seed"
                value={seedInput}
                onChange={(event) => setSeedInput(event.target.value)}
                placeholder="Random"
                error={!seedValid}
                helperText={!seedValid ? 'Enter a whole number or leave blank.' : undefined}
                size="small"
                slotProps={{ htmlInput: { inputMode: 'numeric' } }}
                fullWidth
              />
            </Stack>
          </Stack>
        )}
        {solver === 'dp' && (
          <LossConfigSelect
            id="dp-loss-configs"
            configs={dpLossConfigs}
            selected={dpLossConfigIds}
            onChange={setDpLossConfigIds}
          />
        )}
        {solver === 'sa' && props.agents.length === 1 && (
          <Alert severity="info">Simulated annealing requires at least two agents.</Alert>
        )}
        {props.warning && <Alert severity="warning">{props.warning}</Alert>}
        {props.error && <Alert severity="error">{props.error}</Alert>}
        <Button
          size="large"
          variant="contained"
          disabled={!canSolve || props.loading || props.sampleLoading}
          onClick={() => props.onSolve({
            solver,
            steps: stepsValid ? steps : 50_000,
            runs: runsValid ? runs : 1,
            seed,
            lossConfigIds: solver === 'sa'
              ? lossConfigIds
              : dpLossConfigIds,
          })}
          sx={showProgress ? {
            position: 'relative',
            overflow: 'hidden',
            isolation: 'isolate',
            '&.Mui-disabled': {
              color: '#ffffff',
              backgroundColor: '#b8bec8',
            },
            '&::before': {
              position: 'absolute',
              zIndex: 0,
              inset: 0,
              width: `${progressPercent}%`,
              backgroundColor: 'primary.main',
              content: '""',
              transition: 'width 120ms linear',
            },
          } : undefined}
        >
          <Box component="span" sx={{ position: 'relative', zIndex: 1 }}>
            {props.loading
              ? showProgress
                ? progressLabel
                : 'Optimizing…'
              : 'Optimize tours'}
          </Box>
        </Button>
        {props.result && (
          <ResultsPanel
            result={props.result}
            selectedConfigId={props.selectedConfigId}
            selectedAgentId={props.selectedAgentId}
            onSelectConfig={props.onSelectConfig}
            onSelectAgent={props.onSelectAgent}
          />
        )}
      </Stack>
    </Paper>
  )
}

function parseInteger(value: string): number | undefined {
  if (!/^-?\d+$/.test(value.trim())) return undefined
  const parsed = Number(value)
  return Number.isSafeInteger(parsed) ? parsed : undefined
}

const stateCountFormatter = new Intl.NumberFormat('en', {
  notation: 'compact',
  maximumFractionDigits: 1,
})

function formatStateCount(stateCount: number): string {
  return stateCountFormatter.format(stateCount)
}

function LossConfigSelect({
  id,
  configs,
  selected,
  onChange,
}: {
  id: string
  configs: LossConfig[]
  selected: LossConfigId[]
  onChange: (configIds: LossConfigId[]) => void
}) {
  return (
    <FormControl size="small" fullWidth>
      <InputLabel id={`${id}-label`}>Loss configs</InputLabel>
      <Select
        multiple
        labelId={`${id}-label`}
        label="Loss configs"
        value={selected}
        disabled={configs.length === 0}
        onChange={(event) => {
          const value = event.target.value
          onChange(
            (typeof value === 'string' ? value.split(',') : value) as LossConfigId[],
          )
        }}
        renderValue={(configIds) => configs
          .filter((config) => configIds.includes(config.id))
          .map((config) => config.name)
          .join(', ')}
      >
        {configs.map((config) => (
          <MenuItem key={config.id} value={config.id}>
            <Checkbox checked={selected.includes(config.id)} />
            <ListItemText
              primary={config.name}
              secondary={config.description}
            />
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  )
}

type DraftListProps = {
  agents: AgentDraft[]
  appointments: AppointmentDraft[]
  readOnly: boolean
  onDeleteAgent: (id: string) => void
  onDeleteAppointment: (id: string) => void
}

function DraftList({ agents, appointments, readOnly, onDeleteAgent, onDeleteAppointment }: DraftListProps) {
  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle2">Homes ({agents.length})</Typography>
      {agents.length === 0 ? (
        <Typography variant="body2" color="text.secondary">No homes yet.</Typography>
      ) : (
        agents.map((agent) => (
          <DraftRow
            key={agent.id}
            title={agent.name}
            detail={`${agent.startTime}–${agent.endTime}`}
            onDelete={readOnly ? undefined : () => onDeleteAgent(agent.id)}
          />
        ))
      )}
      <Typography variant="subtitle2">Appointments ({appointments.length})</Typography>
      {appointments.length === 0 ? (
        <Typography variant="body2" color="text.secondary">No appointments yet.</Typography>
      ) : (
        appointments.map((appointment, index) => (
          <DraftRow
            key={appointment.id}
            title={`Appointment ${index + 1}`}
            detail={`${appointment.time} · ${appointment.durationMinutes} min · gain ${appointment.gain}`}
            onDelete={readOnly ? undefined : () => onDeleteAppointment(appointment.id)}
          />
        ))
      )}
    </Stack>
  )
}

function DraftRow({ title, detail, onDelete }: { title: string; detail: string; onDelete?: () => void }) {
  return (
    <Stack direction="row" justifyContent="space-between" alignItems="center" className="draft-row">
      <Box minWidth={0}>
        <Typography variant="body2" fontWeight={700} noWrap>{title}</Typography>
        <Typography variant="caption" color="text.secondary" noWrap>{detail}</Typography>
      </Box>
      {onDelete && <IconButton
        size="small"
        aria-label={`Remove ${title}`}
        title={`Remove ${title}`}
        onClick={onDelete}
        sx={{ color: 'text.primary' }}
      >
        <Box
          component="span"
          aria-hidden
          sx={{ fontSize: '1.35rem', fontWeight: 700, lineHeight: 1 }}
        >
          ×
        </Box>
      </IconButton>}
    </Stack>
  )
}
