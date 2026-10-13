import { get, post, put, del } from './client'

export interface SceneAssets {
  object_classes?: string[]
  rule_ids?: string[]
  action_ids?: string[]
  agent_ids?: string[]
  seats?: string[]
}

export interface SceneRegistryItem {
  id: string
  name: string
  description: string
  icon: string
  color: string
  route: string | null
  assets: SceneAssets | null
  status: 'enabled' | 'disabled' | string
  sort_order: number
  created_at: string | null
  updated_at: string | null
}

export interface SceneRegistryPayload {
  name: string
  description?: string
  icon?: string
  color?: string
  route?: string | null
  status?: 'enabled' | 'disabled'
  sort_order?: number
  assets?: SceneAssets | null
}

export const listScenes = () => get<SceneRegistryItem[]>('/scene-registry')
export const createScene = (body: SceneRegistryPayload) => post<SceneRegistryItem>('/scene-registry', body)
export const updateScene = (id: string, body: Partial<SceneRegistryPayload>) => put<SceneRegistryItem>(`/scene-registry/${id}`, body)
export const deleteScene = (id: string) => del<{ ok: boolean }>(`/scene-registry/${id}`)
