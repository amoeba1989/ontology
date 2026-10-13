import { get, post } from './client'

export interface MilAssessment {
  assessment_id: string
  threat_assessment: string
  ooda_phase: string
  recommended_action: string
  assessed_at: string
  assessed_by: string
  target_id: string
}

export interface MilEvent {
  event_id: string
  event_type: string
  observed_at: string
  confidence: number
  description: string
  target_id: string
}

export interface MilSensor {
  sensor_id: string
  name: string
  sensor_type: string
  coverage_radius_km: number
  is_active: number
}

export interface MilTarget {
  target_id: string
  name: string
  target_type: string
  threat_level: string
  last_known_location: string
  speed_knots: number
  heading_deg: number
  updated_at: string
  event_count: number
  ooda_stage?: OodaStage
  latest_assessment: MilAssessment | null
}

export interface MilOverview {
  targets_total: number
  hostile_targets: number
  active_sensors: number
  sensors_total: number
  events_total: number
  hostile_assessments: number
  assessments_total: number
  threat_distribution: Record<string, number>
  latest_update: string | null
}

export interface MilSituation {
  target: MilTarget
  events: MilEvent[]
  assessments: MilAssessment[]
  sensors: MilSensor[]
  decisions: MilDecision[]
  effects: MilEvent[]
  high_confidence_events: MilEvent[]
  ooda_stage: string
}

export type OodaStage = 'observe' | 'orient' | 'decide' | 'act' | 'closed'

export interface MilDecision {
  decision_id: string
  target_id: string
  assessment_id: string
  confirmed_threat: string
  selected_action_id: string | null
  selected_action_name: string | null
  order_text: string
  decided_by: string
  decided_at: string
  ooda_stage?: string
}

export interface MilDecisionPayload {
  assessment_id: string
  confirmed_threat: string
  selected_action_id?: string | null
  selected_action_name?: string | null
  order_text?: string
  decided_by?: string
}

export interface MilEffectPayload {
  decision_id?: string | null
  effect_description: string
  new_threat?: string | null
}

export interface SceneDataApi {
  overview: () => Promise<MilOverview>
  targets: () => Promise<MilTarget[]>
  situation: (id: string) => Promise<MilSituation>
  createDecision: (id: string, body: MilDecisionPayload) => Promise<MilDecision>
  submitEffect: (id: string, body: MilEffectPayload) => Promise<MilEvent>
}

export function sceneDataApi(prefix: string): SceneDataApi {
  return {
    overview: () => get<MilOverview>(`${prefix}/overview`),
    targets: () => get<MilTarget[]>(`${prefix}/targets`),
    situation: (id: string) => get<MilSituation>(`${prefix}/targets/${id}/situation`),
    createDecision: (id: string, body: MilDecisionPayload) =>
      post<MilDecision>(`${prefix}/targets/${id}/decisions`, body),
    submitEffect: (id: string, body: MilEffectPayload) =>
      post<MilEvent>(`${prefix}/targets/${id}/effects`, body),
  }
}

export const militaryApi = sceneDataApi('/scenes/military')
