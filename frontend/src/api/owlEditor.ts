/**
 * OWL 编辑器 API —— 全部数据走后端（owl_documents 表 + rdflib 解析/导出），无本地演示数据。
 */
import { get, post, put, del } from './client'
import client from './client'
import type { OwlOntology } from '../types/owl'

export interface OwlDocBrief {
  id: string
  name: string
  namespace_iri: string | null
  domain: string | null
  revision: number
  class_count: number
  object_property_count: number
  data_property_count: number
  updated_at: string
}

export interface OwlDocFull extends OwlDocBrief {
  content: Partial<OwlOntology>
}

export interface OwlParseClass {
  iri: string
  localName: string
  label: string | null
  description: string | null
  superClassIRIs: string[]
}

export interface OwlParseProperty {
  iri: string
  localName: string
  label: string | null
  description: string | null
  domainIRIs: string[]
  rangeIRIs: string[]
}

export interface OwlParseResult {
  namespaceIRIs: string[]
  classes: OwlParseClass[]
  objectProperties: OwlParseProperty[]
  dataProperties: OwlParseProperty[]
  errors: string[]
}

function downloadBlob(data: Blob, filename: string) {
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export const owlEditorApi = {
  listDocuments(domain?: string) {
    return get<OwlDocBrief[]>('/owl-editor/documents', { params: domain ? { domain } : {} })
  },

  getDocument(id: string) {
    return get<OwlDocFull>(`/owl-editor/documents/${encodeURIComponent(id)}`)
  },

  createDocument(body: { name: string; namespace_iri?: string; domain?: string | null; content: Partial<OwlOntology> }) {
    return post<OwlDocFull>('/owl-editor/documents', body)
  },

  saveDocument(id: string, body: { content: Partial<OwlOntology>; revision: number; domain?: string | null; namespace_iri?: string }) {
    return put<OwlDocFull>(`/owl-editor/documents/${encodeURIComponent(id)}`, body)
  },

  deleteDocument(id: string) {
    return del<void>(`/owl-editor/documents/${encodeURIComponent(id)}`)
  },

  /** 上传 OWL/TTL → 后端 rdflib 纯解析为编辑器结构（不落库） */
  parseOwl(file: File, fileType: 'xml' | 'turtle' = 'xml') {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('file_type', fileType)
    return post<OwlParseResult>('/owl-editor/parse', fd)
  },

  /** 按场景导出库内本体为 OWL 文件 */
  async exportDbOwl(domain?: string) {
    const res = await client.get('/owl-editor/export', {
      params: domain ? { domain } : {},
      responseType: 'blob',
    })
    downloadBlob(res.data as Blob, `${domain || 'all'}-ontology.owl`)
  },

  /** 当前编辑器草稿导出为 OWL 文件 */
  async exportDraft(iri: string, content: Partial<OwlOntology>) {
    const res = await client.post('/owl-editor/export-draft', { iri, content }, { responseType: 'blob' })
    downloadBlob(res.data as Blob, 'draft-ontology.owl')
  },
}
