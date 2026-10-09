<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'
import { DEFAULT_RETRIEVAL, RETRIEVAL_PRESETS, resolvedCandidateCount, resolvedContextChars,
  retrievalPreset, sanitizeRetrieval, type RetrievalPreferences } from '../utils/retrievalPreferences'

const props = defineProps<{ modelValue: RetrievalPreferences; scopeSummary: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: RetrievalPreferences] }>()
const expanded = ref<'scope' | 'parameters' | null>('scope')
const customSelected = ref(false)
const contextChars = computed(() => resolvedContextChars(props.modelValue))
const candidateCount = computed(() => resolvedCandidateCount(props.modelValue))
const preset = computed(() => customSelected.value ? 'custom' : retrievalPreset(props.modelValue))
const names: Record<string, string> = { fast: '快速', balanced: '均衡', deep: '深入', custom: '自定义' }
function toggle(group: 'scope' | 'parameters') { expanded.value = expanded.value === group ? null : group }
function patch(value: Partial<RetrievalPreferences>) { customSelected.value = true; emit('update:modelValue', sanitizeRetrieval({ ...props.modelValue, ...value })) }
function selectPreset(key: string) {
  customSelected.value = key === 'custom'
  if (key === 'custom') expanded.value = 'parameters'
  else emit('update:modelValue', { ...RETRIEVAL_PRESETS[key]! })
}
function numeric(event: Event): number { return Number((event.target as HTMLInputElement).value) }
function checked(event: Event): boolean { return (event.target as HTMLInputElement).checked }
</script>

<template>
  <section class="qa-side-section qa-settings qa-retrieval-settings">
    <div class="qa-setting-group">
      <button type="button" class="qa-setting-heading" :aria-expanded="expanded === 'scope'" aria-controls="qa-scope-controls" @click="toggle('scope')">
        <span><strong>检索范围</strong><small>{{ scopeSummary }}</small></span>
        <el-icon :class="{ rotated: expanded === 'scope' }"><ArrowRight /></el-icon>
      </button>
      <div v-if="expanded === 'scope'" id="qa-scope-controls" class="qa-setting-body"><slot name="scope" /></div>
    </div>
    <div class="qa-setting-group">
      <button type="button" class="qa-setting-heading" :aria-expanded="expanded === 'parameters'" aria-controls="qa-parameter-controls" @click="toggle('parameters')">
        <span><strong>检索参数</strong><small>{{ names[preset] }} · 目标 {{ modelValue.top_k }} 条 · 重排{{ modelValue.rerank_enabled ? '开启' : '关闭' }}</small></span>
        <el-icon :class="{ rotated: expanded === 'parameters' }"><ArrowRight /></el-icon>
      </button>
      <div class="qa-retrieval-presets" aria-label="检索深度">
        <button v-for="key in ['fast', 'balanced', 'deep', 'custom']" :key="key" type="button" :aria-pressed="preset === key" @click="selectPreset(key)">{{ names[key] }}</button>
      </div>
      <div v-if="expanded === 'parameters'" id="qa-parameter-controls" class="qa-setting-body">
        <div class="qa-slider-field">
          <label for="qa-top-k-number">目标证据数</label>
          <input id="qa-top-k-number" type="number" min="5" max="40" :value="modelValue.top_k" @change="patch({ top_k: numeric($event) })" />
          <input type="range" aria-label="目标证据数滑块" min="5" max="40" step="1" :value="modelValue.top_k" @input="patch({ top_k: numeric($event) })" />
          <small>5～40 条；系统可能补充关键召回，实际数量见回答记录。</small>
        </div>
        <label class="qa-check-setting"><input type="checkbox" :checked="modelValue.rerank_enabled" @change="patch({ rerank_enabled: checked($event) })" />开启重排</label>
        <label class="qa-check-setting"><input type="checkbox" :checked="modelValue.context_auto" @change="patch({ context_auto: checked($event), context_max_chars: contextChars })" />上下文随 Top-K 自动调整</label>
        <p>证据预算：{{ contextChars.toLocaleString() }} 字符</p>
        <details class="qa-advanced-options" :open="customSelected">
          <summary>高级选项</summary>
          <div class="qa-setting-body">
            <label class="qa-check-setting"><input type="checkbox" :checked="modelValue.candidate_top_k === null" @change="patch({ candidate_top_k: checked($event) ? null : candidateCount })" />候选数量自动联动</label>
            <div class="qa-slider-field">
              <label for="qa-candidate-number">候选片段数</label>
              <input id="qa-candidate-number" type="number" :min="Math.max(16, modelValue.top_k)" max="128" :value="candidateCount" :disabled="modelValue.candidate_top_k === null" @change="patch({ candidate_top_k: numeric($event) })" />
              <input type="range" aria-label="候选片段数滑块" :min="Math.max(16, modelValue.top_k)" max="128" :value="candidateCount" :disabled="modelValue.candidate_top_k === null" @input="patch({ candidate_top_k: numeric($event) })" />
            </div>
            <div class="qa-slider-field">
              <label for="qa-context-number">证据上下文上限</label>
              <input id="qa-context-number" type="number" min="8000" max="64000" step="1000" :value="contextChars" :disabled="modelValue.context_auto" @change="patch({ context_max_chars: numeric($event) })" />
              <input type="range" aria-label="证据上下文上限滑块" min="8000" max="64000" step="1000" :value="contextChars" :disabled="modelValue.context_auto" @input="patch({ context_max_chars: numeric($event) })" />
              <small>单位为字符。只发送相关证据，预算不会强行填满；模型窗口至少预留 30% 给输出。</small>
            </div>
          </div>
        </details>
        <button type="button" class="qa-reset-settings" @click="customSelected = false; emit('update:modelValue', { ...DEFAULT_RETRIEVAL })">恢复默认</button>
        <p>记住当前账号在本浏览器的偏好；调整仅影响下一次发送。</p>
      </div>
    </div>
  </section>
</template>
