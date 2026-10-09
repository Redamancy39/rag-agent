<script setup lang="ts">
import type { RetrievalScopeRead } from '../types'
defineProps<{ scope: RetrievalScopeRead }>()
</script>
<template>
  <div v-if="scope.options" class="query-agent-card retrieval-run-summary">
    <strong>本次检索参数与用量</strong>
    <div class="query-agent-grid">
      <span>目标 / 候选</span><p>{{ scope.options.top_k }} / {{ scope.options.candidate_top_k }} 条</p>
      <span>上下文预算</span><p>{{ scope.options.context_max_chars.toLocaleString() }} 字符 · {{ scope.options.context_auto ? '自动' : '手动' }}</p>
      <span>重排设置</span><p>{{ scope.options.rerank_enabled ? '开启' : '关闭' }}</p>
      <span>输出预留</span><p>{{ Math.round(scope.options.output_reserve_ratio * 100) }}%</p>
      <template v-if="scope.usage">
        <span>检索 / 可用证据</span><p>{{ scope.usage.retrieved_count }} / {{ scope.usage.usable_count }} 条</p>
        <span>生成请求</span><p>{{ scope.usage.generation_requested ? '已发起' : '未发起' }}</p>
        <span>上下文准备</span><p>{{ scope.usage.context_evidence_count }} 条 · {{ scope.usage.context_chars.toLocaleString() }} 字符</p>
        <span>实际重排</span><p>{{ scope.usage.rerank_applied ? '已执行' : '未执行' }}</p>
        <span>预算省略</span><p>{{ scope.usage.omitted_count }} 条</p>
        <span>输入 token 保守上界</span><p>{{ scope.usage.input_token_upper_bound?.toLocaleString() ?? '未估算' }}（UTF-8 字节估算）</p>
        <span>API 实际输入 / 输出</span><p>{{ scope.usage.input_tokens?.toLocaleString() ?? '未回传' }} / {{ scope.usage.output_tokens?.toLocaleString() ?? '未回传' }} tokens</p>
        <span v-if="scope.usage.reasoning_tokens !== null">其中推理 tokens</span><p v-if="scope.usage.reasoning_tokens !== null">{{ scope.usage.reasoning_tokens?.toLocaleString() }}</p>
        <span>本次输出上限</span><p>{{ scope.usage.effective_max_output_tokens?.toLocaleString() ?? '未设置' }} tokens</p>
        <span v-if="scope.usage.budget_message">预算说明</span><p v-if="scope.usage.budget_message">{{ scope.usage.budget_message }}</p>
        <span v-if="scope.usage.output_limit_reached">输出说明</span><p v-if="scope.usage.output_limit_reached">达到本次输出上限</p>
      </template>
    </div>
  </div>
</template>
