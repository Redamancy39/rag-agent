<script setup lang="ts">
import { evidenceCollapseNames } from '../../stores/chat'
import { evidenceLocationLabel, getEvidenceRows } from '../../utils/chatResponse'
import { formatScore } from '../../utils/format'
import type { ChatResponse } from '../../types'
defineProps<{ response: ChatResponse; turnId: string }>()
</script>

<template>
                    <el-collapse v-if="response.knowledge_search !== false" v-model="evidenceCollapseNames" class="evidence-collapse">
                      <el-collapse-item :name="turnId">
                        <template #title>
                          <span class="evidence-title">检索片段</span>
                        </template>
                        <el-table
                          v-if="evidenceCollapseNames.includes(turnId)"
                          :data="getEvidenceRows(response)"
                          size="small"
                          class="evidence-table"
                          empty-text="无检索依据"
                        >
                          <el-table-column label="片段" width="70">
                            <template #default="{ row }">{{ row.index }}</template>
                          </el-table-column>
                          <el-table-column label="分数" width="90">
                            <template #default="{ row }">{{ formatScore(row.score) }}</template>
                          </el-table-column>
                          <el-table-column prop="filename" label="文件" min-width="220" show-overflow-tooltip />
                          <el-table-column label="位置" min-width="140" show-overflow-tooltip>
                            <template #default="{ row }">{{ evidenceLocationLabel(row) }}</template>
                          </el-table-column>
                          <el-table-column label="表号" width="120">
                            <template #default="{ row }">{{ row.table || '-' }}</template>
                          </el-table-column>
                          <el-table-column prop="chunk_id" label="块ID" width="150" show-overflow-tooltip />
                          <el-table-column prop="keywords" label="关键字眼" min-width="260" show-overflow-tooltip />
                        </el-table>
                      </el-collapse-item>
                    </el-collapse>
</template>
