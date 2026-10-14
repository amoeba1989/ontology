<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { get, post } from '../../api/client'
const data = ref<any>(null)
const running = ref('')
const error = ref('')
const names: Record<string, string> = { health: '慢病健康管理', library: '学术文献', bim: '建筑运维', supply: '电商供应链' }
async function load() { data.value = await get('/customer-demo/status') }
async function check(key: string) {
  running.value = key; error.value = ''
  try {
    const result = await post<any>(`/customer-demo/${key}/check-ai`)
    if (!result.passed) error.value = result.message
    await load()
  } catch (e: any) { error.value = e.response?.data?.detail || '问答验证失败，请检查模型配置' }
  finally { running.value = '' }
}
onMounted(async () => { try { await load() } catch { error.value = '演示资源加载失败，请刷新重试' } })
</script>

<template>
  <section v-if="data?.packs?.length || error" class="demo-hub">
    <div class="demo-heading"><div><strong>客户演示业务</strong><p>需求 → 数据源 → 数据处理 → 子图建模 → 本体库 → 本体应用</p></div>
      <span>{{ data?.model?.configured ? `系统模型：${data.model.model}` : '模型尚未配置' }}</span></div>
    <p class="demo-note">以下均为独立数据库中的合成演示数据。技能、问答和应用共用已发布的本体数据。</p>
    <div class="demo-grid"><article v-for="pack in data?.packs || []" :key="pack.key">
      <strong>{{ names[pack.key] }}</strong><small>{{ pack.report.objects || 0 }} 类对象 · {{ pack.report.skills || 0 }} 个技能</small>
      <div class="demo-links"><router-link :to="`/apps/projects/${pack.project_id}`">运行应用</router-link>
        <router-link v-if="pack.resources.agent_id" :to="`/agent/manage/${pack.resources.agent_id}`">智能体问答</router-link>
        <router-link v-if="pack.resources.skill_ids?.[0]" :to="`/agent/toolbox/${pack.resources.skill_ids[0]}`">运行技能</router-link></div>
      <small v-if="pack.report.ai">{{ pack.report.ai.passed ? '✓ 问答闭环已验证' : '问答验证未通过' }} · {{ pack.report.ai.model || '未解析到模型' }}<br />{{ new Date(pack.report.ai.checked_at).toLocaleString() }}</small>
      <small v-else>尚未验证模型问答</small>
      <button :disabled="!!running" @click="check(pack.key)">{{ running === pack.key ? '正在调用模型与技能…' : '验证模型问答' }}</button>
    </article></div>
    <p v-if="error" class="demo-error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.demo-hub { padding: 20px; margin: 16px 0; border: 1px solid #dbe5f0; border-radius: 12px; background: #f7faff; color: #183556; }
.demo-heading { display: flex; justify-content: space-between; gap: 20px; align-items: center; }
.demo-heading p, .demo-note { font-size: 12px; color: #5e7085; margin: 7px 0 14px; }.demo-heading span { font-size: 12px; }
.demo-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(205px,1fr)); gap: 12px; }
article { border: 1px solid #e0e8f1; background: white; padding: 16px; border-radius: 8px; } small { display: block; margin: 8px 0; font-size: 11px; color: #5b6b7e; }
.demo-links { display: flex; gap: 12px; font-size: 12px; flex-wrap: wrap; } a { color: #2160a1; }
button { background: #eaf1fa; color: #235d98; padding: 7px 10px; border: 0; border-radius: 5px; cursor: pointer; font-size: 12px; } button:disabled { opacity: .6; }
.demo-error { color: #b42318; font-size: 12px; }
</style>
