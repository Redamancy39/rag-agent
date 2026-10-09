<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'
import { listHotwords, previewQuestion } from '../api/client'
import type { HotwordCatalogue, QueryPreviewRead, QuerySuggestion } from '../types'
import { adoptQuerySuggestion } from '../utils/queryAssistance'

const props = defineProps<{ question: string; token: string }>()
const emit = defineEmits<{ 'update:question': [value: string] }>()
const preview = ref<QueryPreviewRead | null>(null)
const checking = ref(false)
const previewError = ref(false)
const open = ref(false)
const catalogue = ref<HotwordCatalogue | null>(null)
const catalogueError = ref(false)
const search = ref('')
const category = ref('')
const filtered = computed(() => catalogue.value?.entries.filter(entry =>
  (!category.value || entry.category === category.value) &&
  [entry.term, ...entry.aliases, ...entry.typos].some(value => value.toLowerCase().includes(search.value.trim().toLowerCase()))
) ?? [])
const currentPreview = computed(() => preview.value?.original_question === props.question ? preview.value : null)
const matchedTerms = computed(() => [...new Set(currentPreview.value?.hotword_matches.map(item => item.term) ?? [])])

watch(() => [props.question, props.token] as const, ([question, token], _, onCleanup) => {
  preview.value = null
  previewError.value = false
  checking.value = false
  if (!token || !question.trim() || question.length > 4000) return
  const controller = new AbortController()
  let active = true
  const timer = setTimeout(async () => {
    checking.value = true
    try {
      const result = await previewQuestion(token, question, controller.signal)
      if (active) preview.value = result
    } catch {
      if (active) previewError.value = true
    } finally {
      if (active) checking.value = false
    }
  }, 450)
  onCleanup(() => { active = false; clearTimeout(timer); controller.abort() })
}, { immediate: true })

watch(() => [open.value, props.token] as const, async ([expanded, token], _, onCleanup) => {
  catalogue.value = null
  catalogueError.value = false
  if (!expanded || !token) return
  const controller = new AbortController()
  let active = true
  onCleanup(() => { active = false; controller.abort() })
  try {
    const result = await listHotwords(token, controller.signal)
    if (active) catalogue.value = result
  } catch {
    if (active) catalogueError.value = true
  }
}, { immediate: true })

function adopt(suggestion: QuerySuggestion, candidate: string) {
  if (!currentPreview.value) return
  emit('update:question', adoptQuerySuggestion(props.question, currentPreview.value.original_question, suggestion, candidate))
}
</script>

<template>
  <section class="query-assistance" aria-label="食品术语预检">
    <div class="query-assistance-bar">
      <span v-if="checking" role="status">正在检查食品术语…</span>
      <span v-else-if="previewError" role="status">术语预检暂不可用，可提交原问题</span>
      <span v-else-if="currentPreview?.corrections.length" class="query-corrected" role="status">
        已按纠错表修正 {{ currentPreview.corrections.length }} 处
      </span>
      <span v-else-if="currentPreview?.suggestions.length" role="status">发现近似术语，请按需采纳</span>
      <span v-else-if="matchedTerms.length" role="status">已识别 {{ matchedTerms.length }} 个食品术语</span>
      <span v-else>本地术语检查</span>
      <button type="button" class="hotword-toggle" :aria-expanded="open" @click="open = !open">
        食品热词表 <el-icon :class="{ expanded: open }"><ArrowRight /></el-icon>
      </button>
    </div>
    <div v-if="currentPreview && (currentPreview.corrections.length || currentPreview.normalized_question !== question)" class="query-preview">
      <span v-for="item in currentPreview.corrections" :key="item.start" class="query-change">
        {{ item.original }} → <strong>{{ item.replacement }}</strong>
      </span>
      <p><span>检索问题</span>{{ currentPreview.normalized_question }}</p>
    </div>
    <div v-if="currentPreview?.suggestions.length" class="query-suggestions">
      <div v-for="item in currentPreview.suggestions" :key="item.start">
        <span>“{{ item.original }}”是否指</span>
        <button v-for="candidate in item.candidates" :key="candidate" type="button" @click="adopt(item, candidate)">
          {{ candidate }} · 采纳
        </button>
        <span class="query-suggestion-note">未自动修改</span>
      </div>
    </div>
    <div v-if="open" class="hotword-library">
      <div class="hotword-filters">
        <el-input v-model="search" placeholder="搜索术语、简称或错别字" clearable aria-label="搜索食品热词" />
        <el-select v-model="category" placeholder="全部类别" clearable aria-label="食品热词类别">
          <el-option v-for="(label, key) in catalogue?.categories" :key="key" :label="label" :value="key" />
        </el-select>
      </div>
      <p class="hotword-library-note">明确错字按纠错表处理；近似词需采纳。标准号、数值和单位保留。</p>
      <p v-if="catalogueError">热词表加载失败，请收起后重试。</p>
      <p v-else-if="!catalogue">正在加载热词表…</p>
      <template v-else>
        <p class="hotword-library-note">{{ filtered.length }} / {{ catalogue.entries.length }} 个术语 · {{ catalogue.version }}</p>
        <div class="hotword-table-wrap">
          <table class="hotword-table">
            <thead><tr><th>术语</th><th>简称／别名</th><th>配置的错字</th><th>来源</th></tr></thead>
            <tbody>
              <tr v-for="entry in filtered" :key="entry.term">
                <td><strong>{{ entry.term }}</strong><small>{{ catalogue.categories[entry.category] }}</small></td>
                <td>{{ entry.aliases.join('、') || '—' }}</td>
                <td>{{ entry.typos.join('、') || '—' }}</td>
                <td><a :href="entry.source.url" target="_blank" rel="noopener noreferrer" :title="entry.source.title">卫健委</a></td>
              </tr>
              <tr v-if="!filtered.length"><td colspan="4">没有匹配的术语</td></tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.query-assistance { grid-column: 1 / -1; min-width: 0; color: #60758a; font-size: 12px; }
.query-assistance-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.hotword-toggle { display: inline-flex; align-items: center; gap: 5px; padding: 3px 0; background: none; border: 0; color: #008b80; cursor: pointer; font: inherit; }
.hotword-toggle .el-icon { transition: transform .2s ease; }
.hotword-toggle .expanded { transform: rotate(90deg); }
.query-corrected, .query-change strong { color: #008b80; }
.query-preview { margin-top: 7px; border-left: 2px solid #a3dad3; padding: 2px 10px; overflow-wrap: anywhere; }
.query-change { display: inline-block; margin-right: 12px; }
.query-preview p { margin: 5px 0 0; color: #28455c; }
.query-preview p > span { color: #71859a; margin-right: 8px; }
.query-suggestions { margin-top: 6px; max-height: 95px; overflow: auto; }
.query-suggestions button { border: 1px solid #bee5de; border-radius: 5px; background: #f0fbf8; color: #008b80; padding: 3px 7px; margin: 3px 6px; cursor: pointer; font: inherit; }
.query-suggestion-note { color: #8393a4; }
.hotword-library { margin-top: 10px; border-top: 1px solid #e3ecef; padding-top: 10px; }
.hotword-filters { display: grid; grid-template-columns: minmax(0,1fr) 135px; gap: 8px; }
.hotword-library-note { margin: 7px 0; }
.hotword-table-wrap { max-height: 190px; overflow: auto; }
.hotword-table { width: 100%; border-collapse: collapse; text-align: left; }
.hotword-table th { position: sticky; top: 0; background: #f3f7fa; font-weight: 500; }
.hotword-table th, .hotword-table td { padding: 7px 9px; border-bottom: 1px solid #e6eef2; }
.hotword-table small { display: block; margin-top: 2px; font-weight: 400; color: #8796a4; }
.hotword-table a { color: #008b80; }
@media (max-width: 600px) { .hotword-filters { grid-template-columns: minmax(0,1fr) 105px; } }
@media (prefers-reduced-motion: reduce) { .hotword-toggle .el-icon { transition: none; } }
</style>
