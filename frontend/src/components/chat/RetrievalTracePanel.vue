<script setup lang="ts">
import RetrievalRunSummary from '../RetrievalRunSummary.vue'
import { evidenceDecisionLabel, evidenceDecisionType, evidenceLocationLabel, formatSynonymExpansions, getEvidenceDecision, getQueryPlan, getRetrievalScope, getRetrievalTrace, joinPlanItems, retrievalDuration, retrievalScoreBreakdown, retrievalSourceLabel } from '../../utils/chatResponse'
import { formatScore } from '../../utils/format'
import { ref } from 'vue'
import type { ChatResponse } from '../../types'
defineProps<{ response: ChatResponse; turnId: string }>()
const traceOpen = ref<string[]>([])
</script>

<template>
                    <el-collapse
                      v-if="getRetrievalTrace(response).length"
                      v-model="traceOpen"
                      class="retrieval-trace-collapse"
                    >
                      <el-collapse-item :name="`${turnId}-trace`">
                        <template #title>
                          <span class="evidence-title">检索与证据判断过程</span>
                        </template>
                        <div
                          v-if="traceOpen.includes(`${turnId}-trace`) && (getQueryPlan(response) || getEvidenceDecision(response) || getRetrievalScope(response).allowed_document_ids.length)"
                          class="query-agent-summary"
                        >
                          <div class="query-agent-card">
                            <div class="query-agent-card-title">
                              <strong>检索范围</strong>
                              <el-tag size="small" type="success" effect="plain">
                                后端权限过滤
                              </el-tag>
                            </div>
                            <div class="query-agent-grid">
                              <span>用户指定</span>
                              <p>
                                {{
                                  getRetrievalScope(response).requested_document_ids.length
                                    ? `${getRetrievalScope(response).requested_document_ids.length} 个文档`
                                    : '全部可访问文档'
                                }}
                              </p>
                              <span>实际可检索</span>
                              <p>
                                {{ getRetrievalScope(response).allowed_document_ids.length }} 个已入库文档
                              </p>
                              <span>目标证据数</span>
                              <p>Top {{ getRetrievalScope(response).top_k || '-' }}</p>
                            </div>
                          </div>
                          <RetrievalRunSummary :scope="getRetrievalScope(response)" />
                          <div v-if="getQueryPlan(response)" class="query-agent-card">
                            <div class="query-agent-card-title">
                              <strong>查询规范化</strong>
                              <el-tag size="small" effect="plain">
                                {{ getQueryPlan(response)?.source }}
                              </el-tag>
                            </div>
                            <div class="query-agent-grid">
                              <span>归一化问题</span>
                              <p>{{ getQueryPlan(response)?.normalized_question || '-' }}</p>
                              <template v-if="getQueryPlan(response)?.corrections?.length">
                                <span>本地纠错</span>
                                <p>{{ getQueryPlan(response)?.corrections?.map(item => `${item.original} → ${item.replacement}`).join('；') }}</p>
                              </template>
                              <template v-if="getQueryPlan(response)?.lexicon_version">
                                <span>热词表版本</span>
                                <p>{{ getQueryPlan(response)?.lexicon_version }}</p>
                              </template>
                              <span>同义词转换</span>
                              <p>{{ formatSynonymExpansions(getQueryPlan(response)?.synonym_expansions) }}</p>
                              <span>问题类型</span>
                              <p>{{ getQueryPlan(response)?.question_type || '-' }}</p>
                              <span>标准号</span>
                              <p>{{ joinPlanItems(getQueryPlan(response)?.standard_refs) }}</p>
                              <span>核心对象</span>
                              <p>{{ joinPlanItems(getQueryPlan(response)?.entities) }}</p>
                              <span>指标词</span>
                              <p>{{ joinPlanItems(getQueryPlan(response)?.metrics) }}</p>
                              <span>查询分解</span>
                              <p>
                                {{
                                  joinPlanItems(
                                    getQueryPlan(response)?.sub_questions,
                                    '简单问题，无需分解'
                                  )
                                }}
                              </p>
                            </div>
                          </div>
                          <div v-if="getEvidenceDecision(response)" class="query-agent-card">
                            <div class="query-agent-card-title">
                              <strong>证据判断</strong>
                              <el-tag
                                size="small"
                                :type="evidenceDecisionType(response)"
                                effect="plain"
                              >
                                {{ evidenceDecisionLabel(response) }}
                              </el-tag>
                            </div>
                            <div class="query-agent-grid">
                              <span>判断来源</span>
                              <p>{{ getEvidenceDecision(response)?.source || '-' }}</p>
                              <span>置信度</span>
                              <p>{{ formatScore(getEvidenceDecision(response)?.confidence ?? null) }}</p>
                              <span>判断原因</span>
                              <p>{{ getEvidenceDecision(response)?.reason || '-' }}</p>
                              <span>缺失要素</span>
                              <p>{{ joinPlanItems(getEvidenceDecision(response)?.missing_requirements) }}</p>
                            </div>
                          </div>
                        </div>
                        <div v-if="traceOpen.includes(`${turnId}-trace`)" class="retrieval-trace-list">
                          <article
                            v-for="step in getRetrievalTrace(response)"
                            :key="`${turnId}-${step.query_index}-${step.source}`"
                            class="retrieval-trace-step"
                          >
                            <div class="retrieval-trace-head">
                              <el-tag size="small" effect="plain">
                                {{ retrievalSourceLabel(step.source) }}
                              </el-tag>
                              <strong>{{ step.query }}</strong>
                              <span>命中 {{ step.hit_count }} 个</span>
                              <span>耗时 {{ retrievalDuration(step.duration_ms) }}</span>
                            </div>
                            <el-table
                              :data="step.top_hits"
                              size="small"
                              class="evidence-table"
                              empty-text="无命中"
                            >
                              <el-table-column prop="rank" label="#" width="56" />
                              <el-table-column label="采用" width="78">
                                <template #default="{ row }">
                                  <el-tag
                                    v-if="row.selected_for_answer"
                                    size="small"
                                    type="success"
                                    effect="dark"
                                  >
                                    [{{ row.citation_id }}]
                                  </el-tag>
                                  <el-tag
                                    v-else-if="row.preserved_from_pre_rerank"
                                    size="small"
                                    type="info"
                                    effect="plain"
                                  >
                                    保留
                                  </el-tag>
                                  <span v-else>-</span>
                                </template>
                              </el-table-column>
                              <el-table-column label="检索分数" min-width="210">
                                <template #default="{ row }">
                                  <div class="retrieval-score-cell">
                                    <strong>{{ formatScore(row.score) }}</strong>
                                    <span>{{ retrievalScoreBreakdown(row) }}</span>
                                  </div>
                                </template>
                              </el-table-column>
                              <el-table-column prop="filename" label="文件" min-width="220" show-overflow-tooltip />
                              <el-table-column label="位置" min-width="140" show-overflow-tooltip>
                                <template #default="{ row }">{{ evidenceLocationLabel(row) }}</template>
                              </el-table-column>
                              <el-table-column label="来源" width="110">
                                <template #default="{ row }">{{ row.retrieval_source || '-' }}</template>
                              </el-table-column>
                              <el-table-column label="关键词" min-width="180" show-overflow-tooltip>
                                <template #default="{ row }">{{ row.matched_terms?.join('、') || '-' }}</template>
                              </el-table-column>
                              <el-table-column label="片段预览" min-width="260" show-overflow-tooltip>
                                <template #default="{ row }">{{ row.text_preview || '-' }}</template>
                              </el-table-column>
                            </el-table>
                          </article>
                        </div>
                      </el-collapse-item>
                    </el-collapse>
</template>
