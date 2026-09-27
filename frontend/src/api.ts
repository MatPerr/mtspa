import type {
  AgentDraft,
  AppointmentDraft,
  LossConfig,
  OptimizationProgress,
  SampleDataset,
  SolveOptions,
  SolveResult,
} from './types'

export class OptimizationError extends Error {
  constructor(
    message: string,
    readonly code: string,
  ) {
    super(message)
    this.name = 'OptimizationError'
  }
}

const secondsFromMidnight = (value: string): number => {
  const [hours, minutes] = value.split(':').map(Number)
  return hours * 3600 + minutes * 60
}

const timeFromSeconds = (value: number): string => {
  const hours = Math.floor(value / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
}

export type GeocodingSuggestion = {
  latitude: number
  longitude: number
  label: string
}

export async function searchAddresses(
  address: string,
  signal?: AbortSignal,
): Promise<GeocodingSuggestion[]> {
  const query = new URLSearchParams({ query: address, limit: '5' })
  const response = await fetch(`/api/geocode?${query}`, { signal })
  if (!response.ok) {
    throw await responseError(response)
  }
  return (await response.json()) as Array<{
    latitude: number
    longitude: number
    label: string
  }>
}

type SampleProblemResponse = {
  agents: Array<{
    name: string
    latitude: number
    longitude: number
    start_time: number
    end_time: number
  }>
  appointments: Array<{
    latitude: number
    longitude: number
    time: number
    duration: number
    gain: number
  }>
}

export async function loadSampleDatasets(): Promise<SampleDataset[]> {
  const response = await fetch('/api/samples')
  if (!response.ok) {
    throw new Error(`Unable to load sample datasets (${response.status})`)
  }
  return (await response.json()) as SampleDataset[]
}

export async function loadSampleProblem(sampleId: string): Promise<{
  agents: AgentDraft[]
  appointments: AppointmentDraft[]
}> {
  const query = new URLSearchParams({ sample_id: sampleId })
  const response = await fetch(`/api/sample?${query}`)
  if (!response.ok) {
    throw new Error(`Unable to load sample data (${response.status})`)
  }
  const payload = (await response.json()) as SampleProblemResponse
  return {
    agents: payload.agents.map((agent) => ({
      id: crypto.randomUUID(),
      name: agent.name,
      latitude: agent.latitude,
      longitude: agent.longitude,
      startTime: timeFromSeconds(agent.start_time),
      endTime: timeFromSeconds(agent.end_time),
    })),
    appointments: payload.appointments.map((appointment) => ({
      id: crypto.randomUUID(),
      latitude: appointment.latitude,
      longitude: appointment.longitude,
      time: timeFromSeconds(appointment.time),
      durationMinutes: appointment.duration / 60,
      gain: appointment.gain,
    })),
  }
}

export async function loadLossConfigs(): Promise<LossConfig[]> {
  const response = await fetch('/api/loss-configs')
  if (!response.ok) {
    throw new Error(`Unable to load loss configs (${response.status})`)
  }
  return (await response.json()) as LossConfig[]
}

export async function solveProblem(
  agents: AgentDraft[],
  appointments: AppointmentDraft[],
  options: SolveOptions,
  onProgress?: (progress: OptimizationProgress) => void,
): Promise<SolveResult> {
  const { lossConfigIds, ...solverOptions } = options
  const requestBody = JSON.stringify({
    ...solverOptions,
    loss_config_ids: lossConfigIds,
    agents: agents.map((agent) => ({
      name: agent.name,
      latitude: agent.latitude,
      longitude: agent.longitude,
      start_time: secondsFromMidnight(agent.startTime),
      end_time: secondsFromMidnight(agent.endTime),
    })),
    appointments: appointments.map((appointment) => ({
      latitude: appointment.latitude,
      longitude: appointment.longitude,
      time: secondsFromMidnight(appointment.time),
      duration: appointment.durationMinutes * 60,
      gain: appointment.gain,
    })),
  })

  return solveWithProgress(requestBody, onProgress)
}

type SolveStreamEvent =
  | { type: 'progress'; metric: 'steps' | 'states'; current: number; total: number }
  | { type: 'result'; result: SolveResult }
  | { type: 'error'; code: string; detail: string }

async function solveWithProgress(
  requestBody: string,
  onProgress?: (progress: OptimizationProgress) => void,
): Promise<SolveResult> {
  const response = await fetch('/api/solve-stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: requestBody,
  })
  if (!response.ok) {
    throw await responseError(response)
  }
  if (!response.body) {
    throw new Error('The browser could not read the optimization progress stream.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: SolveResult | undefined
  let streamError: { code: string; detail: string } | undefined

  const processLine = (line: string) => {
    if (!line.trim()) return
    const event = JSON.parse(line) as SolveStreamEvent
    if (event.type === 'progress') {
      onProgress?.({
        metric: event.metric,
        current: event.current,
        total: event.total,
      })
    } else if (event.type === 'result') {
      result = event.result
    } else {
      streamError = event
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    lines.forEach(processLine)
    if (done) break
  }
  processLine(buffer)

  if (streamError) {
    throw new OptimizationError(streamError.detail, streamError.code)
  }
  if (!result) throw new Error('Optimization ended without returning a solution.')
  return result
}

async function responseError(response: Response): Promise<Error> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null
  return new Error(payload?.detail ?? `Solve request failed (${response.status})`)
}
