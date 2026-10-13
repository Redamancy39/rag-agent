import { ref } from 'vue'
import type { LlmChunkNormalizationMode } from '../utils/documentStatus.ts'

export const llmChunkNormalizationMode = ref<LlmChunkNormalizationMode>('auto')
export const llmChunkNormalizationOptions = [
  { label: '自动', value: 'auto' },
  { label: '开启', value: 'enabled' },
  { label: '关闭', value: 'disabled' }
]
