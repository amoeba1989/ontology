<template>
  <div class="topology-shell">
    <div ref="containerRef" class="topology-canvas" aria-label="本体关系拓扑画布" />
    <div class="topology-hint">滚轮缩放 · 拖动画布 · 点击对象查看详情 · 双击聚焦一跳关系</div>
    <div v-if="!scene.nodes.length" class="topology-empty">当前场景没有可展示的本体对象</div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import cytoscape, { type Core, type ElementDefinition, type LayoutOptions, type StylesheetJson } from 'cytoscape'
import fcose from 'cytoscape-fcose'
import type { OntologyScene, SceneEvent } from '../../../../api/ontologyScene'

cytoscape.use(fcose)

type LayoutName = 'fcose' | 'concentric' | 'grid'
const props = defineProps<{
  scene: OntologyScene
  selectedId: string | null
  activeEvent: SceneEvent | null
  layoutName: LayoutName
}>()
const emit = defineEmits<{ (e: 'select', id: string | null): void; (e: 'hover', id: string | null): void }>()

const containerRef = ref<HTMLElement | null>(null)
let cy: Core | null = null
let themeObserver: MutationObserver | null = null

function isDark() { return document.documentElement.dataset.theme === 'dark' }

function stylesheet(): StylesheetJson {
  const dark = isDark()
  return [
    { selector: 'node', style: {
      'background-color': 'data(color)', 'border-color': 'data(borderColor)', 'border-width': 2,
      'width': 'data(size)', 'height': 'data(size)', 'shape': 'data(shape)',
      'label': 'data(label)', 'font-size': 11, 'font-weight': 600,
      'color': dark ? '#e9ecef' : '#1f3557', 'text-wrap': 'ellipsis', 'text-max-width': 112,
      'text-valign': 'bottom', 'text-margin-y': 8, 'overlay-opacity': 0,
      'transition-property': 'opacity, border-width, border-color', 'transition-duration': 160,
    } },
    { selector: 'node.draft', style: { 'background-color': dark ? '#555b66' : '#a7b4c8' } },
    { selector: 'node.unbound', style: { 'background-opacity': 0.18, 'border-style': 'dashed' } },
    { selector: 'node.has-rules', style: { 'border-color': '#f59f00', 'border-width': 3 } },
    { selector: 'edge', style: {
      'width': 1.6, 'line-color': dark ? '#596273' : '#a2b5ce',
      'target-arrow-color': dark ? '#7d8da6' : '#849bb8', 'target-arrow-shape': 'triangle',
      'curve-style': 'bezier', 'arrow-scale': 0.8, 'label': 'data(label)',
      'font-size': 9, 'color': dark ? '#aeb7c4' : '#607896',
      'text-background-color': dark ? '#20242b' : '#f7f9fc', 'text-background-opacity': 0.92,
      'text-background-padding': 3, 'text-rotation': 'autorotate', 'overlay-opacity': 0,
      'transition-property': 'opacity, width, line-color, target-arrow-color', 'transition-duration': 160,
    } },
    { selector: '.dimmed', style: { 'opacity': 0.12 } },
    { selector: 'node:selected, node.focused', style: {
      'border-color': '#4c6ef5', 'border-width': 5, 'background-blacken': -0.08,
    } },
    { selector: 'edge.focused', style: {
      'line-color': '#4c6ef5', 'target-arrow-color': '#4c6ef5', 'width': 3.2, 'opacity': 1,
    } },
    { selector: 'node.event-active', style: {
      'border-color': '#e8590c', 'border-width': 6, 'background-blacken': -0.12,
    } },
    { selector: 'edge.event-active', style: {
      'line-color': '#e8590c', 'target-arrow-color': '#e8590c', 'width': 4,
    } },
  ] as StylesheetJson
}

function nodeColor(tier: number) {
  return tier === 1 ? '#4263eb' : tier === 2 ? '#12b886' : '#f08c00'
}

function elements(): ElementDefinition[] {
  const nodes: ElementDefinition[] = props.scene.nodes.map(node => ({
    group: 'nodes',
    data: {
      id: node.id, label: node.name_cn, apiName: node.name, domain: node.domain,
      color: nodeColor(node.tier), borderColor: node.rules.length ? '#f59f00' : nodeColor(node.tier),
      size: Math.min(72, 34 + Math.log10(Math.max(1, node.instance_count) + 1) * 13),
      shape: node.tier === 1 ? 'diamond' : node.tier === 2 ? 'round-rectangle' : 'ellipse',
    },
    classes: [node.status !== 'published' ? 'draft' : '', (!node.source_table || !node.instance_count) ? 'unbound' : '', node.rules.length ? 'has-rules' : ''].filter(Boolean).join(' '),
  }))
  const edges: ElementDefinition[] = props.scene.edges.map(edge => ({
    group: 'edges',
    data: { id: edge.id, source: edge.from_id, target: edge.to_id, label: edge.name_cn || edge.label, cardinality: edge.cardinality },
  }))
  return [...nodes, ...edges]
}

function optionsFor(name: LayoutName): LayoutOptions {
  if (name === 'grid' || props.scene.nodes.length > 800) {
    return { name: 'grid', animate: false, fit: true, padding: 80, avoidOverlap: true } as LayoutOptions
  }
  if (name === 'concentric') {
    return {
      name: 'concentric', animate: props.scene.nodes.length < 300, animationDuration: 420,
      fit: true, padding: 80, minNodeSpacing: 46,
      concentric: node => Number(node.degree()) * 10 + Number(node.data('size')),
      levelWidth: () => 40,
    } as LayoutOptions
  }
  return {
    name: 'fcose', quality: props.scene.nodes.length > 350 ? 'draft' : 'default', randomize: true,
    animate: props.scene.nodes.length < 300, animationDuration: 550, fit: true, padding: 90,
    nodeRepulsion: 6200, idealEdgeLength: 110, edgeElasticity: 0.4, nestingFactor: 0.1,
  } as LayoutOptions
}

function runLayout(name = props.layoutName) {
  if (!cy) return
  cy.layout(optionsFor(name)).run()
}

function updateFocus() {
  if (!cy) return
  cy.elements().removeClass('dimmed focused')
  if (!props.selectedId) return
  const selected = cy.getElementById(props.selectedId)
  if (!selected.length) return
  const neighborhood = selected.closedNeighborhood()
  cy.elements().difference(neighborhood).addClass('dimmed')
  neighborhood.addClass('focused')
}

function updateEvent() {
  if (!cy) return
  cy.elements().removeClass('event-active')
  const event = props.activeEvent
  if (!event) return
  cy.getElementById(event.entity_id).addClass('event-active')
  if (event.relation_id) cy.getElementById(event.relation_id).addClass('event-active')
}

function mountGraph() {
  if (!containerRef.value) return
  cy?.destroy()
  cy = cytoscape({
    container: containerRef.value, elements: elements(), style: stylesheet(),
    minZoom: 0.12, maxZoom: 3, wheelSensitivity: 0.18,
    boxSelectionEnabled: true, selectionType: 'single', pixelRatio: 'auto',
  })
  cy.on('tap', 'node', event => emit('select', event.target.id()))
  cy.on('tap', event => { if (event.target === cy) emit('select', null) })
  cy.on('mouseover', 'node', event => emit('hover', event.target.id()))
  cy.on('mouseout', 'node', () => emit('hover', null))
  cy.on('dbltap', 'node', event => cy?.animate({ fit: { eles: event.target.closedNeighborhood(), padding: 100 }, duration: 350 }))
  cy.on('zoom', () => {
    if (!cy) return
    const visible = cy.zoom() >= 0.62 && props.scene.edges.length < 1200
    cy.style().selector('edge').style('label', visible ? 'data(label)' : '').update()
  })
  runLayout()
  updateFocus()
  updateEvent()
}

function fit() { cy?.animate({ fit: { eles: cy.elements(), padding: 70 }, duration: 320 }) }
function focus(id: string) {
  const node = cy?.getElementById(id)
  if (node?.length) cy?.animate({ center: { eles: node }, zoom: Math.max(0.9, cy.zoom()), duration: 320 })
}
defineExpose({ fit, runLayout, focus })

watch(() => props.scene, mountGraph, { deep: true })
watch(() => props.layoutName, name => runLayout(name))
watch(() => props.selectedId, id => { updateFocus(); if (id) focus(id) })
watch(() => props.activeEvent, updateEvent)

onMounted(() => {
  mountGraph()
  themeObserver = new MutationObserver(() => { if (cy) cy.style(stylesheet()) })
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
})
onBeforeUnmount(() => { themeObserver?.disconnect(); cy?.destroy(); cy = null })
</script>

<style scoped>
.topology-shell{position:absolute;inset:0;background-color:#f6f8fc;background-image:linear-gradient(#dce3ef 1px,transparent 1px),linear-gradient(90deg,#dce3ef 1px,transparent 1px);background-size:24px 24px}.topology-canvas{position:absolute;inset:0}.topology-hint{position:absolute;left:276px;top:86px;padding:6px 10px;border:1px solid #dbe3ef;border-radius:7px;background:rgba(255,255,255,.88);color:#71819a;font-size:11px;pointer-events:none}.topology-empty{position:absolute;inset:0;display:grid;place-items:center;color:#8794a8;font-size:13px;pointer-events:none}
html[data-theme="dark"] .topology-shell{background-color:#17191e;background-image:linear-gradient(#292d35 1px,transparent 1px),linear-gradient(90deg,#292d35 1px,transparent 1px)}html[data-theme="dark"] .topology-hint{background:rgba(32,35,42,.9);border-color:#383e49;color:#9da8b8}
</style>
