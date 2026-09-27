import { useEffect, useState } from 'react'
import { Box, CssBaseline, ThemeProvider } from '@mui/material'
import {
  loadLossConfigs,
  loadSampleDatasets,
  loadSampleProblem,
  OptimizationError,
  solveProblem,
} from './api'
import { MapView } from './components/MapView'
import { ProblemSidebar } from './features/problem/ProblemSidebar'
import { appTheme } from './theme/appTheme'
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
} from './types'

export default function App() {
  const [dataSource, setDataSource] = useState<DataSource>('sample')
  const [manualAgents, setManualAgents] = useState<AgentDraft[]>([])
  const [manualAppointments, setManualAppointments] = useState<AppointmentDraft[]>([])
  const [sampleAgents, setSampleAgents] = useState<AgentDraft[]>([])
  const [sampleAppointments, setSampleAppointments] = useState<AppointmentDraft[]>([])
  const [selectedSampleId, setSelectedSampleId] = useState('')
  const [placementMode, setPlacementMode] = useState<PlacementMode>('agent')
  const [pickedLocation, setPickedLocation] = useState<Coordinate | null>(null)
  const [lossConfigs, setLossConfigs] = useState<LossConfig[]>([])
  const [result, setResult] = useState<SolveResult | null>(null)
  const [selectedConfigId, setSelectedConfigId] = useState<LossConfigId | null>(null)
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [optimizationProgress, setOptimizationProgress] = useState<OptimizationProgress | null>(null)
  const [sampleLoading, setSampleLoading] = useState(false)
  const [sampleDatasets, setSampleDatasets] = useState<SampleDataset[]>([])
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const agents = dataSource === 'sample' ? sampleAgents : manualAgents
  const appointments = dataSource === 'sample' ? sampleAppointments : manualAppointments
  const activeSolution = result?.solutions.find(
    (solution) => solution.loss_config_id === selectedConfigId,
  ) ?? result?.solutions[0]

  useEffect(() => {
    loadLossConfigs()
      .then(setLossConfigs)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : 'Unable to load loss configs.')
      })
  }, [])

  useEffect(() => {
    loadSampleDatasets()
      .then(setSampleDatasets)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : 'Unable to load sample datasets.')
      })
  }, [])

  const invalidateResult = () => {
    setResult(null)
    setSelectedConfigId(null)
    setSelectedAgentId(null)
    setError(null)
    setWarning(null)
  }

  const addAgent = (agent: Omit<AgentDraft, 'id'>) => {
    setManualAgents((current) => [...current, { ...agent, id: crypto.randomUUID() }])
    setPickedLocation(null)
    invalidateResult()
  }

  const addAppointment = (appointment: Omit<AppointmentDraft, 'id'>) => {
    setManualAppointments((current) => [...current, { ...appointment, id: crypto.randomUUID() }])
    setPickedLocation(null)
    invalidateResult()
  }

  const runSolver = async (options: SolveOptions) => {
    setLoading(true)
    setSelectedAgentId(null)
    setOptimizationProgress(options.solver === 'sa'
      ? {
          metric: 'steps',
          current: 0,
          total: options.steps * options.runs * options.lossConfigIds.length,
        }
      : null)
    setError(null)
    setWarning(null)
    try {
      const nextResult = await solveProblem(
        agents,
        appointments,
        options,
        setOptimizationProgress,
      )
      setResult(nextResult)
      setSelectedConfigId(nextResult.solutions[0]?.loss_config_id ?? null)
    } catch (caught) {
      setResult(null)
      setSelectedConfigId(null)
      setSelectedAgentId(null)
      if (caught instanceof OptimizationError && caught.code === 'state_limit_exceeded') {
        setWarning(caught.message)
      } else {
        setError(caught instanceof Error ? caught.message : 'Unable to solve the problem.')
      }
    } finally {
      setLoading(false)
      setOptimizationProgress(null)
    }
  }

  const loadSample = async (sampleId: string) => {
    const previousSampleId = selectedSampleId
    setSelectedSampleId(sampleId)
    setSampleLoading(true)
    invalidateResult()
    try {
      const sample = await loadSampleProblem(sampleId)
      setSampleAgents(sample.agents)
      setSampleAppointments(sample.appointments)
      setPickedLocation(null)
    } catch (caught) {
      setSelectedSampleId(previousSampleId)
      setError(caught instanceof Error ? caught.message : 'Unable to load sample data.')
    } finally {
      setSampleLoading(false)
    }
  }

  return (
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <Box className="app-shell">
        <Box className="map-panel">
          <MapView
            agents={agents}
            appointments={appointments}
            tours={activeSolution?.tours ?? []}
            selectedAgentId={selectedAgentId}
            onMapClick={(coordinate) => {
              if (dataSource === 'manual' && !loading) setPickedLocation(coordinate)
            }}
          />
        </Box>
        <ProblemSidebar
          agents={agents}
          appointments={appointments}
          dataSource={dataSource}
          selectedSampleId={selectedSampleId}
          placementMode={placementMode}
          pickedLocation={pickedLocation}
          loading={loading}
          optimizationProgress={optimizationProgress}
          sampleLoading={sampleLoading}
          sampleDatasets={sampleDatasets}
          error={error}
          warning={warning}
          lossConfigs={lossConfigs}
          result={result}
          selectedConfigId={selectedConfigId}
          selectedAgentId={selectedAgentId}
          onDataSourceChange={(source) => {
            setDataSource(source)
            setPickedLocation(null)
            invalidateResult()
          }}
          onPlacementModeChange={(mode) => {
            setPlacementMode(mode)
            setPickedLocation(null)
          }}
          onAddAgent={addAgent}
          onAddAppointment={addAppointment}
          onLoadSample={loadSample}
          onDeleteAgent={(id) => {
            setManualAgents((current) => current.filter((agent) => agent.id !== id))
            invalidateResult()
          }}
          onDeleteAppointment={(id) => {
            setManualAppointments((current) => current.filter((appointment) => appointment.id !== id))
            invalidateResult()
          }}
          onSolve={runSolver}
          onSelectConfig={(configId) => {
            setSelectedConfigId(configId)
            setSelectedAgentId(null)
          }}
          onSelectAgent={setSelectedAgentId}
        />
      </Box>
    </ThemeProvider>
  )
}
