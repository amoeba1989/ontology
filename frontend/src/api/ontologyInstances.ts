import { get } from './client'

export type OntologyInstance = Record<string, unknown> & { $id: string | number }

export interface InstancePage {
  instances: OntologyInstance[]
  count: number
  limit: number
  offset: number
  asset_id: string
  asset_name: string
  id_column: string
}

export interface InstanceRelation extends Partial<InstancePage> {
  name: string
  label: string
  target?: string
  target_api_name?: string
  status: 'queried' | 'mapping_required'
  instances: OntologyInstance[]
}

export interface InstanceRelations {
  source: OntologyInstance
  relations: InstanceRelation[]
}

const objectPath = (name: string) => `/ontology-api/objects/${encodeURIComponent(name)}`

export const ontologyInstancesApi = {
  list(name: string, offset = 0, limit = 20) {
    return get<InstancePage>(objectPath(name), { params: { offset, limit } })
  },
  detail(name: string, id: string | number) {
    return get<OntologyInstance>(`${objectPath(name)}/${encodeURIComponent(String(id))}`)
  },
  relations(name: string, id: string | number) {
    return get<InstanceRelations>(`${objectPath(name)}/${encodeURIComponent(String(id))}/relations`)
  },
}
