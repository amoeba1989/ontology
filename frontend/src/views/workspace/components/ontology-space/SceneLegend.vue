<template>
  <!-- 常驻图例只讲本体定义（形状=角色、连线=关系）；尺寸/颜色的通道说明收在右侧详情面板「怎么看这张图」 -->
  <div class="scene-legend">
    <span class="lg"><i class="glyph g-node" />类</span>
    <span class="lg"><i class="glyph g-node g-diamond" />规则（条件→行动）</span>
    <span class="lg"><i class="glyph g-tri" />约束（属性校验）</span>
    <span class="lg"><i class="line" />对象属性</span>
    <span class="lg"><i class="arrow" />指向目标类</span>
    <span class="lg"><i class="line line--twin" />多对多</span>
    <span class="lg"><i class="line line--pulse" />事件沿关系传导<em>仅回放时</em></span>
  </div>
</template>

<style scoped>
.scene-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 18px;
  padding: 8px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(160, 187, 226, 0.5);
  backdrop-filter: blur(8px);
  font-family: var(--font-sans);
  font-size: 11.5px;
  color: #46628c;
  pointer-events: none;
}
.lg { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.lg em { font-style: normal; color: #8aa3c8; font-size: 10.5px; }

/* 三个形态标记统一用一种墨色：这里只表达「形状=角色」，不承载颜色通道 */
.glyph { display: inline-block; background: #3b5bdb; flex: none; }
.g-node { width: 11px; height: 11px; border-radius: 50%; }
.g-diamond { width: 9px; height: 9px; border-radius: 1px; transform: rotate(45deg); }
.g-tri {
  width: 0;
  height: 0;
  background: transparent;
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-bottom: 11px solid #3b5bdb;
}

.line { width: 20px; height: 0; display: inline-block; border-top: 2px solid #7d9ec9; flex: none; }
.line--twin { height: 5px; border-top: 2px solid #7d9ec9; border-bottom: 2px solid #7d9ec9; }
.line--pulse { height: 3px; border-top: 0; border-radius: 2px; background: #748ffc; }
.arrow {
  width: 0;
  height: 0;
  display: inline-block;
  flex: none;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 9px solid #7d9ec9;
}
</style>
