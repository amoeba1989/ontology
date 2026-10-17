<template>
  <div class="wve-root">
    <!-- ── 顶部工具栏：文档持久化 + 建模 + 导入导出（全部走后端 API） ── -->
    <div class="wve-toolbar">
      <div class="wve-toolbar__group">
        <span class="wve-toolbar__label">文档</span>
        <select class="wve-select" :value="store.docId ?? ''" @change="onOpenDoc">
          <option value="" disabled>{{ store.docList.length ? '选择文档…' : '暂无文档' }}</option>
          <option v-for="d in store.docList" :key="d.id" :value="d.id">
            {{ d.name }}（{{ d.class_count }}类/{{ d.domain || '未分场景' }}）
          </option>
        </select>
        <button class="wve-btn" @click="onNewDoc">新建</button>
        <button class="wve-btn wve-btn--primary" :disabled="store.saving" @click="onSave">
          {{ store.saving ? '保存中…' : '保存' }}
        </button>
        <input
          v-model="domainInput" class="wve-input wve-input--domain"
          placeholder="场景标签（drone / shopping）" title="保存文档时归属的场景标签"
        />
        <span v-if="store.docId" class="wve-toolbar__meta">rev {{ store.docRevision }}</span>
        <span v-if="saveMsg" class="wve-toolbar__msg" :class="{ 'wve-toolbar__msg--err': saveErr }">{{ saveMsg }}</span>
      </div>

      <div class="wve-toolbar__sep"></div>

      <div class="wve-toolbar__group">
        <button class="wve-btn" @click="onAddClass">+ 类</button>
        <button class="wve-btn" :disabled="!selectedClass" @click="onAddAttr">+ 属性</button>
        <button class="wve-btn" :disabled="!canUndo" @click="onUndo" title="撤销">↩</button>
        <button class="wve-btn" :disabled="!canRedo" @click="onRedo" title="重做">↪</button>
      </div>

      <div class="wve-toolbar__sep"></div>

      <div class="wve-toolbar__group">
        <button class="wve-btn" @click="onImport">导入 OWL</button>
        <button class="wve-btn" @click="onExportDraft">导出 OWL</button>
        <button class="wve-btn" :title="'按场景导出库内本体'" @click="onExportDb">导出库内</button>
      </div>

      <span style="flex:1"></span>

      <span class="wve-toolbar__info">
        类 {{ classes.length }} · 对象属性 {{ objProps.length }} · 数据属性 {{ dataProps.length }}
      </span>
    </div>

    <div class="wve-main">
      <!-- ── VueFlow 画布 ── -->
      <div class="wve-canvas">
        <VueFlow
          v-if="flowNodes.length > 0"
          v-model:nodes="flowNodes"
          v-model:edges="flowEdges"
          :default-edge-options="defaultEdgeOptions"
          :fit-view-on-init="true"
          :fit-view-options="{ padding: 0.15 }"
          :delete-key-code="null"
          :pro-options="{ hideAttribution: true }"
          @connect="onConnect"
          @node-click="onNodeClick"
          @edge-click="onEdgeClick"
          @pane-click="clearSelection"
          @node-drag-stop="onNodeDragStop"
        >
          <Background variant="dots" :gap="22" :size="1" pattern-color="#2c2c50" />
          <Controls position="bottom-left" :show-interactive="false" />
          <MiniMap position="bottom-right" pannable zoomable />

          <!-- 类节点：卡片（名称 + 属性 chips） -->
          <template #node-owlClass="{ data, selected }">
            <div class="wve-node" :class="{ 'wve-node--selected': selected }">
              <Handle type="target" :position="Position.Left" />
              <Handle type="source" :position="Position.Right" />
              <div class="wve-node__head" :style="{ borderColor: data.color }">
                <span class="wve-node__dot" :style="{ background: data.color }"></span>
                <span class="wve-node__name">{{ data.name }}</span>
                <span v-if="data.label" class="wve-node__cn">{{ data.label }}</span>
              </div>
              <div v-if="data.attrs.length" class="wve-node__attrs">
                <span v-for="a in data.attrs.slice(0, 6)" :key="a.id" class="wve-node__attr">
                  {{ a.name }}<i v-if="a.required" class="wve-node__req">*</i>
                </span>
                <span v-if="data.attrs.length > 6" class="wve-node__attr wve-node__attr--more">
                  +{{ data.attrs.length - 6 }}
                </span>
              </div>
            </div>
          </template>
        </VueFlow>

        <div v-else class="wve-empty">
          <div class="wve-empty__icon">◇</div>
          <div class="wve-empty__title">空画布</div>
          <div class="wve-empty__desc">
            点击「+ 类」开始建模，或「导入 OWL」加载已有本体文件
            <br />拖拽节点右侧圆点连接到另一个类，即可创建对象属性
          </div>
        </div>
      </div>

      <!-- ── 右侧编辑侧栏 ── -->
      <aside class="wve-sidebar" :class="{ 'wve-sidebar--open': !!selectedClass || !!selectedProp }">
        <!-- 类编辑 -->
        <template v-if="selectedClass">
          <div class="wve-side__header">
            <span class="wve-side__dot" :style="{ background: CLASS_COLOR }"></span>
            类 · {{ selectedClass.localName }}
          </div>
          <div class="wve-side__section">
            <label class="wve-side__label">英文名（localName）</label>
            <input class="wve-input" :value="selectedClass.localName"
                   @change="renameClass(($event.target as HTMLInputElement).value)" />
          </div>
          <div class="wve-side__section">
            <label class="wve-side__label">中文名（rdfs:label）</label>
            <input class="wve-input" :value="classLabel"
                   @change="setAnnotation(selectedClass, 'rdfs:label', ($event.target as HTMLInputElement).value)" />
          </div>
          <div class="wve-side__section">
            <label class="wve-side__label">描述（rdfs:comment）</label>
            <textarea class="wve-input" rows="2" :value="classComment"
                      @change="setAnnotation(selectedClass, 'rdfs:comment', ($event.target as HTMLTextAreaElement).value)"></textarea>
          </div>
          <div class="wve-side__section">
            <label class="wve-side__label">父类（subClassOf）</label>
            <select class="wve-select" :value="classParentId" @change="setClassParent(($event.target as HTMLSelectElement).value)">
              <option value="">无</option>
              <option v-for="c in classes.filter(x => x.id !== selectedClass!.id)" :key="c.id" :value="c.id">
                {{ c.localName }}
              </option>
            </select>
          </div>
          <div class="wve-side__section">
            <label class="wve-side__label">IRI</label>
            <div class="wve-side__iri">{{ selectedClass.iri }}</div>
          </div>

          <div class="wve-side__section">
            <div class="wve-side__label-row">
              <label class="wve-side__label">数据属性（{{ classAttrs.length }}）</label>
              <button class="wve-btn wve-btn--sm" @click="onAddAttr">+ 添加</button>
            </div>
            <div v-for="a in classAttrs" :key="a.id" class="wve-attr-row">
              <input class="wve-input wve-input--attr" :value="a.localName"
                     @change="renameAttr(a, ($event.target as HTMLInputElement).value)" />
              <select class="wve-select wve-select--type" :value="attrType(a)"
                      @change="setAttrType(a, ($event.target as HTMLSelectElement).value)">
                <option value="string">文本</option>
                <option value="number">数值</option>
                <option value="boolean">布尔</option>
                <option value="date">时间</option>
              </select>
              <button class="wve-btn wve-btn--sm wve-btn--danger" title="删除属性" @click="removeAttr(a)">×</button>
            </div>
            <div v-if="!classAttrs.length" class="wve-side__hint">暂无属性；也可在画布上拖拽连线建立类间关系</div>
          </div>

          <button class="wve-btn wve-btn--danger wve-side__delete" @click="removeClass">删除此类</button>
        </template>

        <!-- 对象属性编辑 -->
        <template v-else-if="selectedProp">
          <div class="wve-side__header">
            <span class="wve-side__dot" :style="{ background: REL_COLOR }"></span>
            对象属性 · {{ selectedProp.localName }}
          </div>
          <div class="wve-side__section">
            <label class="wve-side__label">属性名</label>
            <input class="wve-input" :value="selectedProp.localName"
                   @change="renameProp(($event.target as HTMLInputElement).value)" />
          </div>
          <div class="wve-side__section">
            <label class="wve-side__label">定义域（domain，源）</label>
            <select class="wve-select" :value="classIdByIri(selectedProp.domains[0])"
                    @change="setPropDomain(($event.target as HTMLSelectElement).value)">
              <option value="" disabled>选择源类</option>
              <option v-for="c in classes" :key="c.id" :value="c.id">{{ c.localName }}</option>
            </select>
          </div>
          <div class="wve-side__section">
            <label class="wve-side__label">值域（range，目标）</label>
            <select class="wve-select" :value="classIdByIri(selectedProp.ranges[0])"
                    @change="setPropRange(($event.target as HTMLSelectElement).value)">
              <option value="" disabled>选择目标类</option>
              <option v-for="c in classes" :key="c.id" :value="c.id">{{ c.localName }}</option>
            </select>
          </div>
          <div class="wve-side__section">
            <label class="wve-side__label">特征</label>
            <div class="wve-checks">
              <label v-for="ch in CHARACTS" :key="ch" class="wve-checks__item">
                <input type="checkbox" :checked="selectedProp.characteristics.includes(ch)"
                       @change="toggleChar(ch)" /> {{ ch }}
              </label>
            </div>
          </div>
          <div class="wve-side__section">
            <label class="wve-side__label">IRI</label>
            <div class="wve-side__iri">{{ selectedProp.iri }}</div>
          </div>
          <button class="wve-btn wve-btn--danger wve-side__delete" @click="removeProp">删除此关系</button>
        </template>

        <div v-else class="wve-side__placeholder">点击节点 / 连线进行编辑<br />拖拽节点间连线可新建对象属性</div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { VueFlow, Handle, MarkerType, useVueFlow, Position } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import type { Node, Edge, Connection, NodeMouseEvent, EdgeMouseEvent, NodeDragEvent } from '@vue-flow/core'

import { useOwlEditorStore } from '../../../store/owlEditor'
import { owlEditorApi } from '../../../api/owlEditor'
import type { OwlClass, OwlDataProperty, OwlObjectProperty, ObjectPropertyCharacteristic } from '../../../types/owl'
import { uid } from '../../../utils/owl/iri'

const store = useOwlEditorStore()
const { fitView } = useVueFlow()

const CLASS_COLOR = '#5b9bd5'
const REL_COLOR = '#7b68ee'

const CHARACTS: ObjectPropertyCharacteristic[] = [
  'functional', 'inverseFunctional', 'transitive', 'symmetric', 'asymmetric', 'reflexive', 'irreflexive',
]

const flowNodes = ref<Node[]>([])
const flowEdges = ref<Edge[]>([])
const selectedClassId = ref<string | null>(null)
const selectedPropId = ref<string | null>(null)
const domainInput = ref('')
const saveMsg = ref('')
const saveErr = ref(false)

const defaultEdgeOptions = { type: 'default', markerEnd: MarkerType.ArrowClosed }

const classes = computed(() => store.ontology.classes)
const objProps = computed(() => store.ontology.objectProperties)
const dataProps = computed(() => store.ontology.dataProperties)

const canUndo = computed(() => (store as any).undoStack?.length > 0)
const canRedo = computed(() => (store as any).redoStack?.length > 0)

const selectedClass = computed(() => classes.value.find(c => c.id === selectedClassId.value) || null)
const selectedProp = computed(() => objProps.value.find(p => p.id === selectedPropId.value) || null)

// ── 派生查询 ──

function labelOf(c: OwlClass): string {
  const ann = c.annotations.find(a => a.property === 'rdfs:label')
  return ann?.value || ''
}

function commentOf(c: OwlClass): string {
  const ann = c.annotations.find(a => a.property === 'rdfs:comment')
  return ann?.value || ''
}

function attrType(a: OwlDataProperty): string {
  const xsd = a.ranges[0] || ''
  if (xsd.includes('boolean')) return 'boolean'
  if (xsd.includes('int') || xsd.includes('decimal') || xsd.includes('double') || xsd.includes('float')) return 'number'
  if (xsd.includes('dateTime') || xsd.includes('date')) return 'date'
  return 'string'
}

const XSD_BY_TYPE: Record<string, string> = {
  string: 'http://www.w3.org/2001/XMLSchema#string',
  number: 'http://www.w3.org/2001/XMLSchema#decimal',
  boolean: 'http://www.w3.org/2001/XMLSchema#boolean',
  date: 'http://www.w3.org/2001/XMLSchema#dateTime',
}

function classAttrsOf(c: OwlClass): OwlDataProperty[] {
  return dataProps.value.filter(p => p.domains.includes(c.iri))
}

function classIdByIri(iri?: string): string {
  if (!iri) return ''
  return classes.value.find(c => c.iri === iri)?.id || ''
}

const classLabel = computed(() => (selectedClass.value ? labelOf(selectedClass.value) : ''))
const classComment = computed(() => (selectedClass.value ? commentOf(selectedClass.value) : ''))
const classParentId = computed(() => {
  const sup = selectedClass.value?.superClassExpressions.find(e => e.type === 'namedClass')
  return sup?.classIRI ? classIdByIri(sup.classIRI) : ''
})
const classAttrs = computed(() => (selectedClass.value ? classAttrsOf(selectedClass.value) : []))

// ── 画布构建 ──

function rebuild() {
  const nodes: Node[] = []
  const edges: Edge[] = []

  // 类节点：有坐标用坐标，否则网格布局
  const COLS = 4
  const GAP_X = 300
  const GAP_Y = 190
  classes.value.forEach((c, i) => {
    const pos = (c as any)._pos as { x: number; y: number } | undefined
    nodes.push({
      id: c.id,
      type: 'owlClass',
      position: pos ? { x: pos.x, y: pos.y } : { x: (i % COLS) * GAP_X + 60, y: Math.floor(i / COLS) * GAP_Y + 60 },
      data: {
        name: c.localName,
        label: labelOf(c),
        color: CLASS_COLOR,
        attrs: classAttrsOf(c).map(a => ({ id: a.id, name: a.localName, required: false })),
      },
    })
  })

  const iriToId = new Map(classes.value.map(c => [c.iri, c.id]))

  // 对象属性 → 带标签连线
  for (const p of objProps.value) {
    const src = p.domains[0] ? iriToId.get(p.domains[0]) : null
    const tgt = p.ranges[0] ? iriToId.get(p.ranges[0]) : null
    if (!src || !tgt) continue
    edges.push({
      id: `rel-${p.id}`,
      source: src,
      target: tgt,
      label: p.localName,
      style: { stroke: '#7b68ee', strokeWidth: 1.6 },
      labelStyle: { fill: '#b9aefc', fontSize: 10 },
      labelBgStyle: { fill: '#1a1a2e' },
      data: { propId: p.id },
    })
  }

  // subClassOf → 虚线连线
  for (const c of classes.value) {
    for (const sup of c.superClassExpressions) {
      if (sup.type !== 'namedClass' || !sup.classIRI) continue
      const parentId = iriToId.get(sup.classIRI)
      if (!parentId) continue
      edges.push({
        id: `sub-${c.id}-${sup.id}`,
        source: c.id,
        target: parentId,
        style: { stroke: '#5a6a8a', strokeWidth: 1.2, strokeDasharray: '6 4' },
        data: { kind: 'subclass' },
      })
    }
  }

  flowNodes.value = nodes
  flowEdges.value = edges
}

// ── 交互 ──

function onNodeClick(e: NodeMouseEvent) {
  selectedClassId.value = e.node.id
  selectedPropId.value = null
}

function onEdgeClick(e: EdgeMouseEvent) {
  const propId = e.edge.data?.propId as string | undefined
  if (!propId) return
  selectedPropId.value = propId
  selectedClassId.value = null
}

function clearSelection() {
  selectedClassId.value = null
  selectedPropId.value = null
}

function onNodeDragStop(e: NodeDragEvent) {
  const node = e.node
  const c = classes.value.find(x => x.id === node.id)
  if (c) (c as any)._pos = { x: node.position.x, y: node.position.y }
}

function onConnect(conn: Connection) {
  const src = classes.value.find(c => c.id === conn.source)
  const tgt = classes.value.find(c => c.id === conn.target)
  if (!src || !tgt || src.id === tgt.id) return
  const p = store.addObjectProperty()
  const name = `rel_${src.localName}_to_${tgt.localName}`.slice(0, 60)
  store.updateObjectProperty(p.id, {
    localName: name,
    iri: `${store.ontology.namespaces[0]?.iri || `${store.ontology.iri}#`}${name}`,
    domains: [src.iri],
    ranges: [tgt.iri],
  })
  selectedPropId.value = p.id
  selectedClassId.value = null
  rebuild()
}

// ── 类操作 ──

function onAddClass() {
  const c = store.addClass()
  const n = classes.value.length
  ;(c as any)._pos = { x: 60 + (n % 4) * 300, y: 60 + Math.floor(n / 4) * 190 }
  selectedClassId.value = c.id
  selectedPropId.value = null
  rebuild()
}

function renameClass(newName: string) {
  if (!selectedClass.value || !newName.trim()) return
  const base = store.ontology.namespaces[0]?.iri || `${store.ontology.iri}#`
  store.updateClass(selectedClass.value.id, { localName: newName.trim(), iri: `${base}${newName.trim()}` })
  rebuild()
}

function setAnnotation(c: OwlClass, property: string, value: string) {
  const others = c.annotations.filter(a => a.property !== property)
  const annotations = value.trim() ? [...others, { id: uid('ann'), property, value: value.trim() }] : others
  store.updateClass(c.id, { annotations })
  rebuild()
}

function setClassParent(parentId: string) {
  if (!selectedClass.value) return
  const parent = classes.value.find(c => c.id === parentId)
  store.updateClass(selectedClass.value.id, {
    superClassExpressions: parent
      ? [{ id: uid('expr'), type: 'namedClass' as const, classIRI: parent.iri }]
      : [],
  })
  rebuild()
}

function removeClass() {
  if (!selectedClass.value) return
  // 级联清理：删除关联对象属性与以该类为 domain 的数据属性
  const iri = selectedClass.value.iri
  for (const p of objProps.value.filter(p => p.domains.includes(iri) || p.ranges.includes(iri))) {
    store.deleteObjectProperty(p.id)
  }
  for (const a of dataProps.value.filter(a => a.domains.includes(iri))) {
    store.deleteDataProperty(a.id)
  }
  store.deleteClass(selectedClass.value.id)
  clearSelection()
  rebuild()
}

// ── 数据属性操作 ──

function onAddAttr() {
  if (!selectedClass.value) return
  const a = store.addDataProperty()
  store.updateDataProperty(a.id, { domains: [selectedClass.value.iri] })
  rebuild()
}

function renameAttr(a: OwlDataProperty, newName: string) {
  if (!newName.trim()) return
  const base = store.ontology.namespaces[0]?.iri || `${store.ontology.iri}#`
  store.updateDataProperty(a.id, { localName: newName.trim(), iri: `${base}${newName.trim()}` })
  rebuild()
}

function setAttrType(a: OwlDataProperty, type: string) {
  store.updateDataProperty(a.id, { ranges: [XSD_BY_TYPE[type] || XSD_BY_TYPE.string] })
  rebuild()
}

function removeAttr(a: OwlDataProperty) {
  store.deleteDataProperty(a.id)
  rebuild()
}

// ── 对象属性操作 ──

function renameProp(newName: string) {
  if (!selectedProp.value || !newName.trim()) return
  const base = store.ontology.namespaces[0]?.iri || `${store.ontology.iri}#`
  store.updateObjectProperty(selectedProp.value.id, { localName: newName.trim(), iri: `${base}${newName.trim()}` })
  rebuild()
}

function setPropDomain(classId: string) {
  if (!selectedProp.value) return
  const c = classes.value.find(x => x.id === classId)
  if (c) store.updateObjectProperty(selectedProp.value.id, { domains: [c.iri] })
  rebuild()
}

function setPropRange(classId: string) {
  if (!selectedProp.value) return
  const c = classes.value.find(x => x.id === classId)
  if (c) store.updateObjectProperty(selectedProp.value.id, { ranges: [c.iri] })
  rebuild()
}

function toggleChar(ch: ObjectPropertyCharacteristic) {
  if (!selectedProp.value) return
  const cur = selectedProp.value.characteristics
  store.updateObjectProperty(selectedProp.value.id, {
    characteristics: cur.includes(ch) ? cur.filter(x => x !== ch) : [...cur, ch],
  })
}

function removeProp() {
  if (!selectedProp.value) return
  store.deleteObjectProperty(selectedProp.value.id)
  clearSelection()
  rebuild()
}

// ── 文档持久化 ──

function flash(msg: string, err = false) {
  saveMsg.value = msg
  saveErr.value = err
  if (!err) setTimeout(() => { if (saveMsg.value === msg) saveMsg.value = '' }, 2600)
}

async function onOpenDoc(e: Event) {
  const id = (e.target as HTMLSelectElement).value
  if (!id) return
  try {
    await store.openDocument(id)
    domainInput.value = store.docDomain
    flash(`已打开「${store.docName}」`)
    rebuild()
    await nextTick()
    fitView({ padding: 0.15 })
  } catch {
    flash('打开文档失败', true)
  }
}

async function onNewDoc() {
  const name = window.prompt('新文档名称：')
  if (!name?.trim()) return
  const res = await store.saveDocument(name.trim(), domainInput.value || undefined)
  flash(res.message, !res.ok)
  if (res.ok) rebuild()
}

async function onSave() {
  const res = await store.saveDocument(undefined, domainInput.value || undefined)
  flash(res.message, !res.ok)
  if (!res.ok && !store.docId) {
    const name = window.prompt('首次保存需要文档名：')
    if (name?.trim()) {
      const r2 = await store.saveDocument(name.trim(), domainInput.value || undefined)
      flash(r2.message, !r2.ok)
    }
  }
}

// ── 导入导出（后端 rdflib） ──

function onImport() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.owl,.xml,.rdf,.ttl'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const res = await store.importOwlFile(file)
      if (res.errors.length) flash(res.errors[0], true)
      else flash(`导入成功：${res.classes.length} 类 / ${res.objectProperties.length} 关系 / ${res.dataProperties.length} 属性`)
      rebuild()
      await nextTick()
      fitView({ padding: 0.15 })
    } catch {
      flash('OWL 解析失败（后端 rdflib）', true)
    }
  }
  input.click()
}

async function onExportDraft() {
  try {
    await store.exportCurrentDraft()
    flash('已导出当前草稿为 OWL')
  } catch {
    flash('导出失败', true)
  }
}

async function onExportDb() {
  try {
    await owlEditorApi.exportDbOwl(domainInput.value || undefined)
    flash(`已导出库内本体（${domainInput.value || '全部场景'}）`)
  } catch {
    flash('导出库内本体失败', true)
  }
}

function onUndo() {
  store.undo()
  clearSelection()
  rebuild()
}

function onRedo() {
  store.redo()
  clearSelection()
  rebuild()
}

// ── 生命周期 ──

onMounted(async () => {
  await store.refreshDocList()
  // 自动打开最近编辑的文档
  if (store.docList.length && !store.docId) {
    try {
      await store.openDocument(store.docList[0].id)
      domainInput.value = store.docDomain
      rebuild()
      await nextTick()
      fitView({ padding: 0.15 })
    } catch { /* 打开失败保持空画布 */ }
  } else {
    rebuild()
  }
})

watch(() => store.docVersion, () => rebuild())
</script>

<style scoped>
.wve-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #0f1120;
  color: #e0e0e0;
  font-size: 12px;
  position: relative;
  overflow: hidden;
}

/* 工具栏 */
.wve-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #14172b;
  border-bottom: 1px solid #2a2a4a;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.wve-toolbar__group { display: flex; align-items: center; gap: 6px; }
.wve-toolbar__label { font-size: 11px; color: #8892b0; }
.wve-toolbar__meta { font-size: 10px; color: #5b9bd5; }
.wve-toolbar__info { font-size: 11px; color: #8892b0; }
.wve-toolbar__msg { font-size: 11px; color: #58d68d; }
.wve-toolbar__msg--err { color: #e57373; }
.wve-toolbar__sep { width: 1px; height: 18px; background: #2a2a4a; }

.wve-btn {
  padding: 4px 10px;
  border: 1px solid #3a3a5a;
  border-radius: 4px;
  background: #232744;
  color: #e0e0e0;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}
.wve-btn:hover { background: #2f3458; }
.wve-btn:disabled { opacity: 0.4; cursor: default; }
.wve-btn--primary { background: #4a6fa5; border-color: #5a8fd4; }
.wve-btn--primary:hover { background: #5a8fd4; }
.wve-btn--danger { background: #8b2020; border-color: #a03030; }
.wve-btn--danger:hover { background: #a03030; }
.wve-btn--sm { padding: 2px 7px; font-size: 10px; }

.wve-select {
  max-width: 260px;
  padding: 3px 6px;
  border: 1px solid #3a3a5a;
  border-radius: 4px;
  background: #0f1120;
  color: #e0e0e0;
  font-size: 11px;
}
.wve-select--type { width: 58px; }

.wve-input {
  padding: 4px 8px;
  border: 1px solid #3a3a5a;
  border-radius: 4px;
  background: #0f1120;
  color: #e0e0e0;
  font-size: 12px;
  width: 100%;
  box-sizing: border-box;
}
.wve-input--domain { width: 190px; }
.wve-input--attr { flex: 1; }
textarea.wve-input { resize: vertical; }

/* 主区 */
.wve-main { flex: 1; display: flex; overflow: hidden; position: relative; }
.wve-canvas { flex: 1; overflow: hidden; background: radial-gradient(ellipse at center, #14172b 0%, #0b0d18 100%); }

/* 类节点卡片 */
.wve-node {
  min-width: 170px;
  max-width: 240px;
  background: #181b30;
  border: 1px solid #2f3458;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.45);
  cursor: grab;
}
.wve-node--selected { border-color: #38bdf8; box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.35); }
.wve-node__head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border-bottom: 2px solid;
}
.wve-node__dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.wve-node__name { font-weight: 600; font-size: 12px; }
.wve-node__cn { font-size: 10px; color: #8892b0; margin-left: auto; }
.wve-node__attrs { padding: 6px 10px 8px; display: flex; flex-wrap: wrap; gap: 4px; }
.wve-node__attr {
  font-size: 10px;
  color: #9fd6a9;
  background: rgba(60, 179, 113, 0.12);
  border: 1px solid rgba(60, 179, 113, 0.3);
  border-radius: 3px;
  padding: 1px 5px;
}
.wve-node__attr--more { color: #8892b0; background: transparent; border-color: #2f3458; }
.wve-node__req { color: #e57373; font-style: normal; }

/* 空状态 */
.wve-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  text-align: center;
}
.wve-empty__icon { font-size: 40px; color: #2f3458; }
.wve-empty__title { font-size: 15px; color: #8892b0; }
.wve-empty__desc { font-size: 11px; color: #555f7d; line-height: 1.8; }

/* 侧栏 */
.wve-sidebar {
  width: 0;
  background: #14172b;
  border-left: 1px solid #2a2a4a;
  overflow-y: auto;
  flex-shrink: 0;
  transition: width 0.18s ease;
}
.wve-sidebar--open { width: 300px; padding: 14px; }
.wve-side__header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 14px;
}
.wve-side__dot { width: 10px; height: 10px; border-radius: 50%; }
.wve-side__section { margin-bottom: 12px; }
.wve-side__label { display: block; font-size: 10px; color: #8892b0; text-transform: uppercase; margin-bottom: 4px; }
.wve-side__label-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.wve-side__iri { font-size: 10px; color: #555f7d; word-break: break-all; }
.wve-side__hint { font-size: 10px; color: #555f7d; line-height: 1.6; }
.wve-side__placeholder { font-size: 11px; color: #555f7d; text-align: center; padding: 40px 10px; line-height: 2; }
.wve-side__delete { width: 100%; margin-top: 4px; }

.wve-attr-row { display: flex; gap: 4px; margin-bottom: 5px; align-items: center; }

.wve-checks { display: flex; flex-wrap: wrap; gap: 4px 10px; }
.wve-checks__item { display: flex; align-items: center; gap: 4px; font-size: 11px; color: #aab4d4; cursor: pointer; }
</style>
