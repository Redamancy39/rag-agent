<script setup lang="ts">
import { computed } from 'vue'
import type { ChatResponse, Citation } from '../../types'
import { citationById, citationLocationLabel } from '../../utils/chatResponse'

const props = defineProps<{
  response?: ChatResponse
  citationId?: number | null
  citation?: Citation
  label?: string
  chip?: boolean
  index?: number
}>()

const resolved = computed(() => props.citation || (props.response && props.citationId != null ? citationById(props.response, props.citationId) : undefined))
const marker = computed(() => props.citation?.citation_id || props.citationId || ((props.index ?? -1) >= 0 ? (props.index || 0) + 1 : ''))
</script>

<template>
  <el-popover trigger="click" placement="top" :width="420">
    <template #reference>
      <button type="button" :class="chip ? 'citation-chip' : 'inline-citation'" :aria-label="`查看引用 ${marker} 的原文`">
        <template v-if="chip">[{{ marker }}] {{ citation?.filename }} · {{ citationLocationLabel(citation) }}<template v-if="citation?.table"> · {{ citation.table }}</template></template>
        <template v-else>{{ label }}</template>
      </button>
    </template>
    <div class="citation-popover">
      <strong>[{{ marker }}] {{ resolved?.filename || citation?.filename || '来源不存在' }}</strong>
      <span>{{ citationLocationLabel(resolved || citation) }} · {{ (resolved || citation)?.table || '无表号' }} · {{ (resolved || citation)?.chunk_id || '无块 ID' }}</span>
      <p>{{ resolved?.text || citation?.text || '未找到对应来源' }}</p>
    </div>
  </el-popover>
</template>
