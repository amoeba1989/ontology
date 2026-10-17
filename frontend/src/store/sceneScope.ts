import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { listScenes, type SceneRegistryItem } from '../api/sceneRegistry'
import { useOntologyStore } from './ontology'

export const SCENE_STORAGE_KEY = 'ontology.selected-scene'
export const useSceneScope = defineStore('scene-scope', () => {
  const scenes = ref<SceneRegistryItem[]>([])
  const selectedId = ref(localStorage.getItem(SCENE_STORAGE_KEY) ?? '')
  const ready = ref(false)
  const error = ref('')
  const current = computed(() => scenes.value.find(s => s.id === selectedId.value))
  async function load() {
    error.value = ''
    try {
      scenes.value = (await listScenes()).filter(s => s.status === 'enabled')
      const saved = localStorage.getItem(SCENE_STORAGE_KEY)
      if (saved === null || (saved && !scenes.value.some(s => s.id === saved))) {
        selectedId.value = scenes.value.find(s => s.id === 'scene_drone')?.id ?? scenes.value[0]?.id ?? ''
      }
      localStorage.setItem(SCENE_STORAGE_KEY, selectedId.value)
      saveDomain()
      ready.value = true
    } catch {
      error.value = '场景列表加载失败，请重试'
    }
  }
  function select(id: string) {
    const ontology = useOntologyStore()
    ontology.entities = []
    ontology.currentEntity = null
    ontology.graphData = null
    selectedId.value = id
    localStorage.setItem(SCENE_STORAGE_KEY, id)
    saveDomain()
  }
  function saveDomain() {
    const domains = current.value?.assets?.domains ?? []
    if (domains.length === 1) localStorage.setItem('ontology.selected-domain', domains[0]!)
    else localStorage.removeItem('ontology.selected-domain')
  }
  return { scenes, selectedId, ready, error, current, load, select }
})
