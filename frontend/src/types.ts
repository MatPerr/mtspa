export type Coordinate = {
  latitude: number
  longitude: number
}

export type AgentDraft = Coordinate & {
  id: string
  name: string
  startTime: string
  endTime: string
}

export type AppointmentDraft = Coordinate & {
  id: string
  time: string
  durationMinutes: number
  gain: number
}

export type PlacementMode = 'agent' | 'appointment'
export type SolverName = 'sa' | 'dp'
export type LossConfigId =
  | 'shortest_distance'
  | 'fair_hourly_pay'
  | 'fair_distance'
  | 'maximum_uptime'

export type OptimizationProgress = {
  metric: 'steps' | 'states'
  current: number
  total: number
}

export type SolutionMetrics = {
  total_distance: number
  distance_std: number
  total_travel_time: number
  travel_time_std: number
  total_gain: number
  gain_std: number
  total_gain_per_km: number
  gain_per_km_std: number
  total_gain_per_hour: number
  gain_per_hour_std: number
  total_lateness: number
  total_waiting_time: number
  waiting_time_std: number
  total_overtime: number
  overtime_std: number
}

export type LossConfig = {
  id: LossConfigId
  name: string
  description: string
  supported_solvers: SolverName[]
  terms: Array<{
    metric: keyof SolutionMetrics
    importance: number
  }>
}

export type TourResult = {
  agent_id: number
  agent_name: string
  node_ids: number[]
  appointment_ids: number[]
  coordinates: Coordinate[]
  metrics: TourMetrics
  timeline: TourTimeline
}

export type TimelineKind = 'travel' | 'waiting' | 'appointment' | 'lateness' | 'overtime' | 'available'

export type TimelineSegment = {
  kind: TimelineKind
  start_time: number
  end_time: number
  appointment_id: number | null
}

export type TourTimeline = {
  end_time: number
  workday_start: number
  workday_end: number
  return_time: number
  segments: TimelineSegment[]
}

export type TourMetrics = {
  distance: number
  travel_time: number
  gain: number
  elapsed_time: number
  gain_per_km: number
  gain_per_hour: number
  lateness: number
  waiting_time: number
  overtime: number
}

export type ConfigSolution = {
  loss_config_id: LossConfigId
  loss_config_name: string
  loss: number
  metrics: SolutionMetrics
  tours: TourResult[]
  final_state_count: number | null
}

export type SolveResult = {
  solver: SolverName
  elapsed_seconds: number
  solutions: ConfigSolution[]
}

export type SolveOptions = {
  solver: SolverName
  steps: number
  runs: number
  seed?: number
  lossConfigIds: LossConfigId[]
}
