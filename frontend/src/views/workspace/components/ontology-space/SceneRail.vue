<template>
  <nav class="rail">
    <div class="rail__search">
      <input v-model="keyword" placeholder="搜索本体 / 属性 / 规则" />
    </div>

    <p v-if="!groups.length" class="rail__none">没有匹配的本体</p>

    <section v-for="g in groups" :key="g.key" class="rail__group">
      <h4>{{ g.label }}<i>{{ g.nodes.length }}</i></h4>
      <div v-for="tier in [1, 2, 3]" :key="tier" class="rail__tier">
        <button
          v-for="n in g.nodes.filter(x => x.tier === tier)"
          :key="n.id"
          type="button"
          class="rail__item"
          :class="{
            'is-on': n.id === selectedId,
            ['shape-' + n.tier]: true,
            'is-draft': n.status !== 'published',
            'is-hollow': !n.instance_count || !n.source_table,
          }"
          @click="emit('focus', n.id)"
        >
          <span class="rail__glyph" />
          <span class="rail__body">
            <b>{{ n.name_cn }}</b>
            <em>{{ n.name }} · T{{ n.tier }}</em>
          </span>
          <span class="rail__nums">
            <u>{{ n.instance_count }}</u>
            <s v-if="n.rules.length">{{ n.rules.length }}规则</s>
          </span>
        </button>
      </div>
    </section>

    <div class="rail__foot">
      <button type="button" class="rail__reset" @click="emit('reset')">适应画布</button>
      <button type="button" class="rail__reset" @click="emit('refresh')">重载数据</button>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { OntologyScene, SceneNode } from '../../../../api/ontologyScene'
import { domainLabel } from './topologyMeta'

const props = defineProps<{
  scene: OntologyScene | null
  selectedId: string | null
}>()

const emit = defineEmits<{ (e: 'focus', id: string): void; (e: 'reset'): void; (e: 'refresh'): void }>()

const keyword = ref('')

const matched = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  const nodes = props.scene?.nodes ?? []
  if (!k) return nodes
  return nodes.filter(n =>
    n.name.toLowerCase().includes(k)
    || n.name_cn.includes(k)
    || n.attributes.some(a => a.name.toLowerCase().includes(k))
    || n.rules.some(r => r.name.toLowerCase().includes(k)),
  )
})

const groups = computed(() => {
  const buckets = new Map<string, SceneNode[]>()
  matched.value.forEach(n => {
    const key = n.domain || ''
    if (!buckets.has(key)) buckets.set(key, [])
    buckets.get(key)!.push(n)
  })
  return Array.from(buckets.entries()).map(([key, nodes]) => ({
    key,
    label: domainLabel(key),
    nodes: [...nodes].sort((a, b) => a.tier - b.tier || a.name.localeCompare(b.name)),
  }))
})
</script>

<style scoped>
.rail {
  position: absolute;
  left: 16px;
  top: 82px;
  /* 让位给底部停靠区（图例 + 事件时间轴），--dock-h 是父级实测出的停靠区占位高度 */
  bottom: 126px;
  z-index: 8;
  width: 236px;
  overflow-y: auto;
  padding: 12px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(160, 187, 226, 0.5);
  box-shadow: 0 14px 34px rgba(46, 87, 148, 0.12);
  backdrop-filter: blur(12px);
  font-family: var(--font-sans);
}
.rail::-webkit-scrollbar { width: 6px; }
.rail::-webkit-scrollbar-thumb { background: rgba(122, 165, 216, 0.45); border-radius: 3px; }

.rail__search input {
  width: 100%;
  box-sizing: border-box;
  padding: 7px 10px;
  border-radius: 9px;
  border: 1px solid rgba(186, 205, 235, 0.8);
  background: #fff;
  font-size: 11.5px;
  color: #2f4670;
  outline: none;
}
.rail__search input:focus { border-color: #4c6ef5; }
.rail__none { margin: 14px 0; font-size: 11px; color: #a7bcd9; text-align: center; }

.rail__group { margin-top: 12px; }
.rail__group h4 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 6px;
  font-size: 11.5px;
  letter-spacing: 0.05em;
  color: #1e3a6b;
}
.rail__group h4 i {
  font-style: normal;
  font-size: 9.5px;
  padding: 0 5px;
  border-radius: 999px;
  background: rgba(76, 110, 245, 0.12);
  color: #4263eb;
}
.rail__tier { display: flex; flex-direction: column; gap: 4px; margin-bottom: 6px; }

.rail__item {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 6px 8px;
  text-align: left;
  border: 1px solid transparent;
  border-radius: 9px;
  background: rgba(244, 248, 253, 0.85);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.rail__item:hover { background: #fff; border-color: rgba(186, 200, 255, 0.9); }
.rail__item.is-on { background: #eef2ff; border-color: #4c6ef5; }
/* 与三维场景同一套形态编码：形状=角色，颜色=发布状态，空心=无数据 */
.rail__glyph { width: 9px; height: 9px; border-radius: 2px; background: #3b5bdb; flex: 0 0 auto; }
.shape-1 .rail__glyph { transform: rotate(45deg); }
.shape-2 .rail__glyph { width: 15px; height: 7px; border-radius: 999px; }
.shape-3 .rail__glyph { width: 7px; height: 12px; }
.rail__item.is-draft .rail__glyph { background: #8fa0b8; }
.rail__item.is-hollow .rail__glyph { background: transparent; border: 1.4px solid #8fa0b8; }
.rail__body { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.rail__body b { font-size: 12px; color: #22406e; }
.rail__body em { font-style: normal; font-size: 9.5px; color: #93aecf; }
.rail__nums { display: flex; flex-direction: column; align-items: flex-end; gap: 1px; }
.rail__nums u { text-decoration: none; font-size: 11px; color: #4c6ef5; font-weight: 600; }
.rail__nums s { text-decoration: none; font-size: 9px; color: #e8590c; }

.rail__foot { display: flex; gap: 6px; margin-top: 10px; }
.rail__reset {
  flex: 1;
  padding: 6px 0;
  border-radius: 8px;
  border: 1px solid rgba(186, 205, 235, 0.8);
  background: #fff;
  color: #46628c;
  font-size: 11px;
  cursor: pointer;
}
.rail__reset:hover { border-color: #4c6ef5; color: #3b5bdb; }

/* ── 深色态覆盖 ── */
html[data-theme="dark"] .rail { background: rgba(33, 34, 38, 0.86); border-color: rgba(255, 255, 255, 0.08); box-shadow: 0 14px 34px rgba(0, 0, 0, 0.45); }
html[data-theme="dark"] .rail::-webkit-scrollbar-thumb { background: rgba(122, 123, 130, 0.5); }
html[data-theme="dark"] .rail__search input { background: #1a1b1e; border-color: #37383d; color: #f1f2f4; }
html[data-theme="dark"] .rail__search input:focus { border-color: #5c7cfa; }
html[data-theme="dark"] .rail__none { color: #7a7b82; }
html[data-theme="dark"] .rail__group h4 { color: #c1c2c5; }
html[data-theme="dark"] .rail__group h4 i { background: rgba(92, 124, 250, 0.18); color: #91a7ff; }
html[data-theme="dark"] .rail__item { background: rgba(44, 45, 49, 0.6); }
html[data-theme="dark"] .rail__item:hover { background: #2c2d31; border-color: rgba(92, 124, 250, 0.45); }
html[data-theme="dark"] .rail__item.is-on { background: rgba(76, 110, 245, 0.16); border-color: #5c7cfa; }
html[data-theme="dark"] .rail__glyph { background: #91a7ff; }
html[data-theme="dark"] .rail__item.is-draft .rail__glyph { background: #7a7b82; }
html[data-theme="dark"] .rail__item.is-hollow .rail__glyph { background: transparent; border-color: #7a7b82; }
html[data-theme="dark"] .rail__body b { color: #e0e1e3; }
html[data-theme="dark"] .rail__body em { color: #868e96; }
html[data-theme="dark"] .rail__nums u { color: #91a7ff; }
html[data-theme="dark"] .rail__nums s { color: #ffa94d; }
html[data-theme="dark"] .rail__reset { background: #212226; border-color: #37383d; color: #c1c2c5; }
html[data-theme="dark"] .rail__reset:hover { border-color: #5c7cfa; color: #dbe4ff; }
</style>
