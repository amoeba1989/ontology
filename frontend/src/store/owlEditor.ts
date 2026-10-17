import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { OwlOntology, OwlClass, OwlObjectProperty, OwlDataProperty, OwlIndividual, OwlAnnotation, ObjectPropertyCharacteristic, OwlNamespace } from '../types/owl'
import { uid } from '../utils/owl/iri'
// 前端序列化/解析仍被 Protege 编辑器视图使用；WebVowl 编辑器统一走后端 owlEditorApi
import { serializeToOwlXml, downloadOwlFile } from '../utils/owl/serializer'
import { parseOwlXml } from '../utils/owl/parser'
import { owlEditorApi } from '../api/owlEditor'
import type { OwlDocBrief, OwlParseResult } from '../api/owlEditor'

function createEmptyOntology(): OwlOntology {
  return {
    id: uid('ont'),
    iri: 'http://yuanshu.ontology/local#',
    annotations: [],
    namespaces: [{ prefix: 'ys', iri: 'http://yuanshu.ontology/local#' }],
    classes: [],
    objectProperties: [],
    dataProperties: [],
    individuals: [],
  }
}

/** 补齐后端文档 content 中缺失的数组字段，保证结构完整 */
function normalizeContent(raw: Partial<OwlOntology> | undefined | null): OwlOntology {
  const base = createEmptyOntology()
  if (!raw) return base
  return {
    ...base,
    ...raw,
    iri: raw.iri || base.iri,
    namespaces: raw.namespaces?.length ? raw.namespaces : base.namespaces,
    annotations: raw.annotations ?? [],
    classes: raw.classes ?? [],
    objectProperties: raw.objectProperties ?? [],
    dataProperties: raw.dataProperties ?? [],
    individuals: raw.individuals ?? [],
  }
}

export const useOwlEditorStore = defineStore('owlEditor', () => {
  const ontology = ref<OwlOntology>(createEmptyOntology())
  const selectedTab = ref<string>('classes')
  const selectedClassId = ref<string | null>(null)
  const selectedObjectPropertyId = ref<string | null>(null)
  const selectedDataPropertyId = ref<string | null>(null)
  const selectedIndividualId = ref<string | null>(null)
  const isDirty = ref(false)

  const undoStack = ref<string[]>([])
  const redoStack = ref<string[]>([])
  const MAX_UNDO = 50

  function snapshot() {
    undoStack.value.push(JSON.stringify(ontology.value))
    if (undoStack.value.length > MAX_UNDO) undoStack.value.shift()
    redoStack.value = []
    isDirty.value = true
  }

  function undo() {
    const prev = undoStack.value.pop()
    if (!prev) return
    redoStack.value.push(JSON.stringify(ontology.value))
    ontology.value = JSON.parse(prev)
  }

  function redo() {
    const next = redoStack.value.pop()
    if (!next) return
    undoStack.value.push(JSON.stringify(ontology.value))
    ontology.value = JSON.parse(next)
  }

  // Computed
  const selectedClass = computed(() => ontology.value.classes.find(c => c.id === selectedClassId.value) || null)
  const selectedObjectProperty = computed(() => ontology.value.objectProperties.find(p => p.id === selectedObjectPropertyId.value) || null)
  const selectedDataProperty = computed(() => ontology.value.dataProperties.find(p => p.id === selectedDataPropertyId.value) || null)
  const selectedIndividual = computed(() => ontology.value.individuals.find(i => i.id === selectedIndividualId.value) || null)

  const metrics = computed(() => ({
    classCount: ontology.value.classes.length,
    objectPropertyCount: ontology.value.objectProperties.length,
    dataPropertyCount: ontology.value.dataProperties.length,
    individualCount: ontology.value.individuals.length,
  }))

  // Class CRUD
  function addClass(parentIRI?: string): OwlClass {
    snapshot()
    const base = ontology.value.namespaces[0]?.iri || `${ontology.value.iri}#`
    const localName = `NewClass${ontology.value.classes.length + 1}`
    const c: OwlClass = {
      id: uid('cls'),
      iri: `${base}${localName}`,
      localName,
      annotations: [],
      superClassExpressions: parentIRI ? [{ id: uid('expr'), type: 'namedClass', classIRI: parentIRI }] : [],
      equivalentClassExpressions: [],
      disjointWith: [],
    }
    ontology.value.classes.push(c)
    selectedClassId.value = c.id
    return c
  }

  function deleteClass(id: string) {
    snapshot()
    ontology.value.classes = ontology.value.classes.filter(c => c.id !== id)
    if (selectedClassId.value === id) selectedClassId.value = null
  }

  function updateClass(id: string, patch: Partial<OwlClass>) {
    snapshot()
    const idx = ontology.value.classes.findIndex(c => c.id === id)
    if (idx >= 0) ontology.value.classes[idx] = { ...ontology.value.classes[idx], ...patch }
  }

  // Object Property CRUD
  function addObjectProperty(parentIRI?: string): OwlObjectProperty {
    snapshot()
    const base = ontology.value.namespaces[0]?.iri || `${ontology.value.iri}#`
    const localName = `newObjectProperty${ontology.value.objectProperties.length + 1}`
    const p: OwlObjectProperty = {
      id: uid('op'),
      iri: `${base}${localName}`,
      localName,
      annotations: [],
      superProperties: parentIRI ? [parentIRI] : [],
      domains: [],
      ranges: [],
      characteristics: [],
      inverseOf: null,
    }
    ontology.value.objectProperties.push(p)
    selectedObjectPropertyId.value = p.id
    return p
  }

  function deleteObjectProperty(id: string) {
    snapshot()
    ontology.value.objectProperties = ontology.value.objectProperties.filter(p => p.id !== id)
    if (selectedObjectPropertyId.value === id) selectedObjectPropertyId.value = null
  }

  function updateObjectProperty(id: string, patch: Partial<OwlObjectProperty>) {
    snapshot()
    const idx = ontology.value.objectProperties.findIndex(p => p.id === id)
    if (idx >= 0) ontology.value.objectProperties[idx] = { ...ontology.value.objectProperties[idx], ...patch }
  }

  // Data Property CRUD
  function addDataProperty(parentIRI?: string): OwlDataProperty {
    snapshot()
    const base = ontology.value.namespaces[0]?.iri || `${ontology.value.iri}#`
    const localName = `newDataProperty${ontology.value.dataProperties.length + 1}`
    const p: OwlDataProperty = {
      id: uid('dp'),
      iri: `${base}${localName}`,
      localName,
      annotations: [],
      superProperties: parentIRI ? [parentIRI] : [],
      domains: [],
      ranges: [],
      functional: false,
    }
    ontology.value.dataProperties.push(p)
    selectedDataPropertyId.value = p.id
    return p
  }

  function deleteDataProperty(id: string) {
    snapshot()
    ontology.value.dataProperties = ontology.value.dataProperties.filter(p => p.id !== id)
    if (selectedDataPropertyId.value === id) selectedDataPropertyId.value = null
  }

  function updateDataProperty(id: string, patch: Partial<OwlDataProperty>) {
    snapshot()
    const idx = ontology.value.dataProperties.findIndex(p => p.id === id)
    if (idx >= 0) ontology.value.dataProperties[idx] = { ...ontology.value.dataProperties[idx], ...patch }
  }

  // Individual CRUD
  function addIndividual(): OwlIndividual {
    snapshot()
    const base = ontology.value.namespaces[0]?.iri || `${ontology.value.iri}#`
    const localName = `individual${ontology.value.individuals.length + 1}`
    const ind: OwlIndividual = {
      id: uid('ind'),
      iri: `${base}${localName}`,
      localName,
      annotations: [],
      types: [],
      objectPropertyAssertions: [],
      dataPropertyAssertions: [],
      sameAs: [],
      differentFrom: [],
    }
    ontology.value.individuals.push(ind)
    selectedIndividualId.value = ind.id
    return ind
  }

  function deleteIndividual(id: string) {
    snapshot()
    ontology.value.individuals = ontology.value.individuals.filter(i => i.id !== id)
    if (selectedIndividualId.value === id) selectedIndividualId.value = null
  }

  function updateIndividual(id: string, patch: Partial<OwlIndividual>) {
    snapshot()
    const idx = ontology.value.individuals.findIndex(i => i.id === id)
    if (idx >= 0) ontology.value.individuals[idx] = { ...ontology.value.individuals[idx], ...patch }
  }

  // Ontology meta
  function updateOntologyMeta(patch: Partial<Pick<OwlOntology, 'iri' | 'versionIRI' | 'annotations' | 'namespaces'>>) {
    snapshot()
    Object.assign(ontology.value, patch)
  }

  // Serialization
  function exportOwlXml(): string {
    return serializeToOwlXml(ontology.value)
  }

  function exportAndDownload(filename?: string) {
    downloadOwlFile(ontology.value, filename)
  }

  function importOwlXml(xmlString: string) {
    snapshot()
    ontology.value = parseOwlXml(xmlString)
    selectedClassId.value = null
    selectedObjectPropertyId.value = null
    selectedDataPropertyId.value = null
    selectedIndividualId.value = null
  }

  function newOntology(iri?: string) {
    snapshot()
    ontology.value = createEmptyOntology()
    if (iri) ontology.value.iri = iri
    selectedClassId.value = null
    selectedObjectPropertyId.value = null
    selectedDataPropertyId.value = null
    selectedIndividualId.value = null
    isDirty.value = false
  }

  // Persistence（owl_documents 表，revision 乐观锁）
  const docId = ref<string | null>(null)
  const docName = ref('')
  const docDomain = ref('')
  const docRevision = ref(0)
  const docList = ref<OwlDocBrief[]>([])
  const saving = ref(false)
  /** 每次整体替换文档时自增，画布 watch 它触发重渲染（类数量不变时也能刷新） */
  const docVersion = ref(0)

  function _clearSelection() {
    selectedClassId.value = null
    selectedObjectPropertyId.value = null
    selectedDataPropertyId.value = null
    selectedIndividualId.value = null
  }

  function _applyDocMeta(d: { id: string; name: string; domain: string | null; revision: number; content: Partial<OwlOntology> }) {
    docId.value = d.id
    docName.value = d.name
    docDomain.value = d.domain || ''
    docRevision.value = d.revision
    ontology.value = normalizeContent(d.content)
    _clearSelection()
    isDirty.value = false
    docVersion.value++
  }

  async function refreshDocList(domain?: string) {
    docList.value = await owlEditorApi.listDocuments(domain)
    return docList.value
  }

  async function newDocument(name: string, domain?: string) {
    saving.value = true
    try {
      const d = await owlEditorApi.createDocument({ name, domain: domain || null, content: ontology.value })
      _applyDocMeta(d)
      await refreshDocList()
      return d
    } finally { saving.value = false }
  }

  async function openDocument(id: string) {
    const d = await owlEditorApi.getDocument(id)
    _applyDocMeta(d)
    return d
  }

  /** 保存当前文档；未关联文档时需传 name 新建 */
  async function saveDocument(name?: string, domain?: string): Promise<{ ok: boolean; message: string }> {
    saving.value = true
    try {
      if (!docId.value) {
        if (!name) return { ok: false, message: '首次保存需要文档名' }
        const d = await owlEditorApi.createDocument({ name, domain: domain || null, content: ontology.value })
        _applyDocMeta(d)
        await refreshDocList()
        return { ok: true, message: `已创建文档「${d.name}」` }
      }
      const d = await owlEditorApi.saveDocument(docId.value, {
        content: ontology.value,
        revision: docRevision.value,
        domain: domain ?? (docDomain.value || null),
      })
      docRevision.value = d.revision
      isDirty.value = false
      await refreshDocList()
      return { ok: true, message: `已保存（revision ${d.revision}）` }
    } catch (e: unknown) {
      const resp = (e as { response?: { status?: number; data?: { detail?: string } } })?.response
      if (resp?.status === 409) {
        return { ok: false, message: resp.data?.detail || '文档已被他人修改，请刷新后重试' }
      }
      return { ok: false, message: resp?.data?.detail || '保存失败' }
    } finally { saving.value = false }
  }

  async function deleteCurrentDocument() {
    if (!docId.value) return
    await owlEditorApi.deleteDocument(docId.value)
    docId.value = null
    docName.value = ''
    docRevision.value = 0
    await refreshDocList()
  }

  /** 导入 OWL/TTL：后端 rdflib 解析（与平台口径一致），结果映射为编辑器文档 */
  async function importOwlFile(file: File) {
    const fileType = file.name.endsWith('.ttl') ? 'turtle' : 'xml'
    const res = await owlEditorApi.parseOwl(file, fileType)
    _applyParseResult(res)
    return res
  }

  function _applyParseResult(res: OwlParseResult) {
    snapshot()
    const namespaces: OwlNamespace[] = res.namespaceIRIs.map((iri, i) => ({ prefix: `ns${i + 1}`, iri }))
    const primaryIri = namespaces[0]?.iri || 'http://yuanshu.ontology/local#'
    ontology.value = {
      id: uid('ont'),
      iri: primaryIri,
      annotations: [],
      namespaces,
      classes: res.classes.map(c => ({
        id: uid('cls'),
        iri: c.iri,
        localName: c.localName,
        annotations: [
          ...(c.label ? [{ id: uid('ann'), property: 'rdfs:label', value: c.label }] : []),
          ...(c.description ? [{ id: uid('ann'), property: 'rdfs:comment', value: c.description }] : []),
        ],
        superClassExpressions: c.superClassIRIs.map(iri => ({ id: uid('expr'), type: 'namedClass' as const, classIRI: iri })),
        equivalentClassExpressions: [],
        disjointWith: [],
      })),
      objectProperties: res.objectProperties.map(p => ({
        id: uid('op'),
        iri: p.iri,
        localName: p.localName,
        annotations: [
          ...(p.label ? [{ id: uid('ann'), property: 'rdfs:label', value: p.label }] : []),
        ],
        superProperties: [],
        domains: p.domainIRIs,
        ranges: p.rangeIRIs,
        characteristics: [],
        inverseOf: null,
      })),
      dataProperties: res.dataProperties.map(p => ({
        id: uid('dp'),
        iri: p.iri,
        localName: p.localName,
        annotations: [
          ...(p.label ? [{ id: uid('ann'), property: 'rdfs:label', value: p.label }] : []),
        ],
        superProperties: [],
        domains: p.domainIRIs,
        ranges: p.rangeIRIs,
        functional: false,
      })),
      individuals: [],
    }
    docId.value = null
    docName.value = ''
    docRevision.value = 0
    _clearSelection()
    docVersion.value++
  }

  /** 导出当前草稿为 OWL 文件（后端 rdflib 序列化） */
  async function exportCurrentDraft() {
    await owlEditorApi.exportDraft(ontology.value.iri, ontology.value)
  }

  function saveDraft() {
    // 兼容旧调用：直接走后端保存；无关联文档时忽略（由编辑器引导命名保存）
    if (docId.value) void saveDocument()
  }

  function loadDraft(): boolean {
    // 兼容旧调用：不再读 localStorage；文档加载由 openDocument 完成
    return docId.value !== null
  }

  return {
    ontology, selectedTab, selectedClassId, selectedObjectPropertyId, selectedDataPropertyId, selectedIndividualId, isDirty,
    selectedClass, selectedObjectProperty, selectedDataProperty, selectedIndividual, metrics,
    snapshot, undo, redo,
    addClass, deleteClass, updateClass,
    addObjectProperty, deleteObjectProperty, updateObjectProperty,
    addDataProperty, deleteDataProperty, updateDataProperty,
    addIndividual, deleteIndividual, updateIndividual,
    updateOntologyMeta, exportOwlXml, exportAndDownload, importOwlXml, newOntology,
    docId, docName, docDomain, docRevision, docList, saving, docVersion,
    refreshDocList, newDocument, openDocument, saveDocument, deleteCurrentDocument,
    importOwlFile, exportCurrentDraft,
    saveDraft, loadDraft,
  }
})
