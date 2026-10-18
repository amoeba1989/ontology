<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { get } from '../../api/client'

type Connection = { id:string; name:string; type:string; enabled:boolean; status:string; last_test_ok?:boolean }
const loading=ref(true), connections=ref<Connection[]>([]), loadError=ref('')
const active=computed(()=>connections.value.filter(x=>x.enabled&&x.status==='active').length)
const tested=computed(()=>connections.value.filter(x=>x.last_test_ok).length)
const stages=[
  {no:'01',name:'场景启动',detail:'要地防护想定',route:'/scene/drone',tone:'cyan'},
  {no:'02',name:'态势接入',detail:'MQTT 遥测',route:'/data/connections',tone:'cyan'},
  {no:'03',name:'数据治理',detail:'观测 / 状态 / 目标',route:'/data/assets',tone:'blue'},
  {no:'04',name:'语义映射',detail:'对象与关系',route:'/data/mapping',tone:'blue'},
  {no:'05',name:'威胁研判',detail:'规则与证据',route:'/logic/rules',tone:'purple'},
  {no:'06',name:'方案生成',detail:'技能与智能体',route:'/agent/manage',tone:'purple'},
  {no:'07',name:'处置执行',detail:'行动与命令',route:'/logic/actions',tone:'orange'},
  {no:'08',name:'效果评估',detail:'结果与审计',route:'/ops/log-audit',tone:'green'},
]
onMounted(async()=>{try{connections.value=await get<Connection[]>('/connections',{params:{type:'mqtt'}})}catch{loadError.value='MQTT 状态暂时无法读取'}finally{loading.value=false}})
</script>

<template>
  <section class="cuas-panel">
    <div class="cuas-head">
      <div><span class="cuas-kicker">主演示场景 · MQTT 实时链路</span><h2>反无人机要地防护</h2><p>未知目标进入保护区后，从遥测接入、本体认知、威胁研判到处置评估形成完整闭环。</p></div>
      <div class="cuas-actions">
        <div class="mqtt-state" :class="{warning:!active}"><span class="pulse"/><div><strong>MQTT {{loading?'检查中':active?'已配置':'待配置'}}</strong><small v-if="!loading&&!loadError">{{connections.length}} 个连接 · {{active}} 个启用 · {{tested}} 个测试通过</small><small v-else>{{loadError||'正在读取连接状态…'}}</small></div></div>
        <RouterLink class="secondary" to="/data/connections">配置 MQTT</RouterLink><RouterLink class="primary" to="/scene/drone">进入场景工作台</RouterLink>
      </div>
    </div>
    <div class="stage-grid"><RouterLink v-for="stage in stages" :key="stage.no" :to="stage.route" class="stage" :class="stage.tone"><span class="number">{{stage.no}}</span><strong>{{stage.name}}</strong><small>{{stage.detail}}</small><span class="arrow">→</span></RouterLink></div>
    <div class="cuas-note"><strong>真实入口：</strong>/scene/drone　<span>数据通道：</span>minsim/scenario · minsim/telemetry · minsim/command</div>
  </section>
</template>

<style scoped>
.cuas-panel{padding:22px;margin:16px 0 22px;border:1px solid #b9dff0;border-radius:14px;background:linear-gradient(135deg,#f2fbff 0%,#f6f7ff 55%,#f3fffb 100%);color:#17324d;box-shadow:0 10px 28px rgba(28,95,130,.08)}.cuas-head{display:flex;align-items:flex-start;justify-content:space-between;gap:24px}.cuas-kicker{font-size:11px;letter-spacing:.08em;color:#0682a6;font-weight:800}.cuas-head h2{margin:7px 0 6px;font-size:23px}.cuas-head p{margin:0;max-width:700px;color:#587089;font-size:13px;line-height:1.7}.cuas-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.cuas-actions a{padding:9px 14px;border-radius:7px;font-size:12px;font-weight:700}.cuas-actions .primary{background:#1769e0;color:#fff}.cuas-actions .secondary{background:#fff;border:1px solid #c9d8e8;color:#245b8c}.mqtt-state{display:flex;align-items:center;gap:9px;padding:7px 11px;background:#e8fff7;border:1px solid #a9ead5;border-radius:8px}.mqtt-state.warning{background:#fff8e9;border-color:#f2d49a}.pulse{width:9px;height:9px;border-radius:50%;background:#17b77d;box-shadow:0 0 0 4px rgba(23,183,125,.13)}.warning .pulse{background:#e5a124;box-shadow:0 0 0 4px rgba(229,161,36,.13)}.mqtt-state strong,.mqtt-state small{display:block;white-space:nowrap}.mqtt-state strong{font-size:11px}.mqtt-state small{margin-top:2px;color:#667a8e;font-size:9px}.stage-grid{display:grid;grid-template-columns:repeat(8,minmax(105px,1fr));gap:9px;margin-top:20px}.stage{position:relative;display:flex;min-height:88px;flex-direction:column;padding:12px 11px;border:1px solid #d7e3ed;border-radius:9px;background:#fff;color:#17324d;transition:.18s ease}.stage:hover{transform:translateY(-2px);box-shadow:0 6px 14px rgba(27,70,100,.12)}.stage .number{font-size:10px;font-weight:800}.stage strong{margin-top:9px;font-size:13px}.stage small{margin-top:5px;color:#73869a;font-size:10px}.stage .arrow{position:absolute;right:9px;top:9px;color:#91a3b5}.stage.cyan .number{color:#079bc3}.stage.blue .number{color:#346dee}.stage.purple .number{color:#8454d8}.stage.orange .number{color:#df8428}.stage.green .number{color:#15966c}.cuas-note{margin-top:13px;padding-top:11px;border-top:1px dashed #bfd5e2;font-size:11px;color:#587089}.cuas-note strong{color:#147192}.cuas-note span{font-weight:700;color:#4b6380}html[data-theme="dark"] .cuas-panel{border-color:#244861;background:linear-gradient(135deg,#10283a,#18213c 55%,#102f2c);color:var(--neutral-800)}html[data-theme="dark"] .cuas-head p,html[data-theme="dark"] .cuas-note{color:var(--neutral-600)}html[data-theme="dark"] .stage{background:var(--surface-card);border-color:var(--neutral-200);color:var(--neutral-800)}html[data-theme="dark"] .mqtt-state{background:rgba(23,183,125,.12);border-color:rgba(23,183,125,.35)}html[data-theme="dark"] .cuas-actions .secondary{background:var(--surface-card);border-color:var(--neutral-200);color:var(--semantic-300)}@media(max-width:1200px){.stage-grid{grid-template-columns:repeat(4,1fr)}}@media(max-width:760px){.cuas-head{flex-direction:column}.cuas-actions{justify-content:flex-start}.stage-grid{grid-template-columns:repeat(2,1fr)}}
</style>
