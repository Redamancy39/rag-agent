<script setup lang="ts">
import { loadingChunks, selectedChunks } from '../../stores/documents'
import { chunkOcrSummary, chunkQualityFlags, chunkQualityLabel, chunkQualityScore, chunkQualityTagType, chunkSourceLabel, chunkTypeLabel } from '../../utils/documentStatus'
import { textPreview } from '../../utils/format'
</script>

<template>
        <div v-loading="loadingChunks" class="chunk-dialog-body">
          <el-alert
            type="info"
            show-icon
            :closable="false"
            title="这里展示的是已写入 ChromaDB 的文本分块，适合检查表格转写、页码来源和分块边界。"
          />
          <el-empty v-if="!loadingChunks && selectedChunks.length === 0" description="当前文档暂无可展示分块" />
          <div v-else class="chunk-list">
            <article v-for="chunk in selectedChunks" :key="chunk.id" class="chunk-card">
              <header>
                <div>
                  <strong>{{ chunk.id }}</strong>
                  <span>{{ chunkSourceLabel(chunk) }}</span>
                </div>
                <div class="chunk-tags">
                  <el-tag size="small" effect="plain">{{ chunkTypeLabel(chunk) }}</el-tag>
                  <el-tag size="small" effect="plain" :type="chunkQualityTagType(chunk)">
                    {{ chunkQualityLabel(chunk) }} {{ chunkQualityScore(chunk).toFixed(2) }}
                  </el-tag>
                  <el-tag v-if="chunk.metadata.needs_llm_normalization" size="small" effect="plain" type="warning">
                    待归一化
                  </el-tag>
                  <el-tag v-if="chunk.metadata.llm_normalized" size="small" effect="plain" type="success">
                    LLM归一化
                  </el-tag>
                </div>
              </header>
              <div class="chunk-quality-row">
                <span v-if="chunkOcrSummary(chunk)">{{ chunkOcrSummary(chunk) }}</span>
                <span v-if="chunkQualityFlags(chunk)">Flags: {{ chunkQualityFlags(chunk) }}</span>
              </div>
              <p>{{ textPreview(chunk.text, 1800) }}</p>
            </article>
          </div>
        </div>
</template>
