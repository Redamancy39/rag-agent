<script setup lang="ts">
import { loadingJobs, selectedJobDocument, selectedJobs } from '../../stores/documents'
import { formatPlanSummary, llmCheckLabel, llmCheckType, llmExecutionNote, llmNormalizationLabel, llmNormalizationType, traceDuration, traceItems, traceStateLabel, traceStateType, traceSummaryRows } from '../../utils/documentStatus'
import { formatJson, formatTime } from '../../utils/format'
</script>

<template>
        <div v-loading="loadingJobs" class="job-dialog-body">
          <section v-if="selectedJobDocument" class="document-llm-overview">
            <div class="panel-actions">
              <span>LLM 检测</span>
              <el-tag :type="llmCheckType(selectedJobDocument)" size="small" effect="plain">{{ llmCheckLabel(selectedJobDocument) }}</el-tag>
              <span>大模型整理</span>
              <el-tag :type="llmNormalizationType(selectedJobDocument)" size="small" effect="plain">{{ llmNormalizationLabel(selectedJobDocument) }}</el-tag>
              <span>{{ llmExecutionNote(selectedJobDocument) }}</span>
            </div>
            <p>{{ selectedJobDocument.llm_processing?.detail || '暂无可核验的 LLM 执行记录。' }}</p>
          </section>
          <el-table
            :data="selectedJobs"
            size="small"
            class="job-table"
            empty-text="暂无处理任务"
          >
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="stage" label="阶段" width="130" />
            <el-table-column prop="status" label="状态" width="120" />
            <el-table-column label="处理策略" min-width="280" show-overflow-tooltip>
              <template #default="{ row }">{{ formatPlanSummary(row) }}</template>
            </el-table-column>
            <el-table-column prop="message" label="说明" min-width="300" show-overflow-tooltip />
            <el-table-column label="进度" width="130">
              <template #default="{ row }">
                {{ row.progress_current || 0 }} / {{ row.progress_total || 0 }}
              </template>
            </el-table-column>
            <el-table-column label="开始时间" width="170">
              <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
            </el-table-column>
            <el-table-column label="结束时间" width="170">
              <template #default="{ row }">{{ formatTime(row.finished_at) }}</template>
            </el-table-column>
          </el-table>

          <el-collapse v-if="selectedJobs.length" class="job-detail-collapse">
            <el-collapse-item
              v-for="job in selectedJobs"
              :key="job.id"
              :title="`入库节点追踪 #${job.id}`"
              :name="String(job.id)"
            >
              <section class="job-trace-section">
                <div class="job-trace-head">
                  <h3>节点时间线</h3>
                  <span>展示 FileProbe → StrategyPlanner → Parse/OCR → Normalize → ChunkQuality → Index → Report 的执行结果</span>
                </div>
                <el-timeline v-if="traceItems(job).length" class="job-trace-timeline">
                  <el-timeline-item
                    v-for="item in traceItems(job)"
                    :key="`${job.id}-${item.node}-${item.started_at || item.state}`"
                    :type="traceStateType(item.state)"
                    :timestamp="formatTime(item.started_at || null)"
                    placement="top"
                  >
                    <div class="job-trace-card">
                      <div class="job-trace-title">
                        <strong>{{ item.label || item.node }}</strong>
                        <el-tag :type="traceStateType(item.state)" size="small" effect="plain">
                          {{ traceStateLabel(item.state) }}
                        </el-tag>
                      </div>
                      <p>{{ item.message || '-' }}</p>
                      <p v-if="item.finished_at">结束时间：{{ formatTime(item.finished_at) }}；耗时：{{ traceDuration(item) }}</p>
                      <p v-if="item.error" class="job-trace-error">错误：{{ item.error }}</p>
                      <div v-if="traceSummaryRows(item).length" class="job-trace-summary">
                        <span
                          v-for="row in traceSummaryRows(item)"
                          :key="`${item.node}-${row.key}`"
                        >
                          {{ row.key }}：{{ row.value }}
                        </span>
                      </div>
                    </div>
                  </el-timeline-item>
                </el-timeline>
                <el-empty v-else description="该任务暂无节点追踪记录" :image-size="72" />
              </section>
              <div class="job-detail-grid">
                <section>
                  <h3>处理策略 Plan</h3>
                  <pre class="json-block">{{ formatJson(job.plan_json) }}</pre>
                </section>
                <section>
                  <h3>文件探测 Probe</h3>
                  <pre class="json-block">{{ formatJson(job.probe_json) }}</pre>
                </section>
                <section>
                  <h3>上传选项 Options</h3>
                  <pre class="json-block">{{ formatJson(job.options_json) }}</pre>
                </section>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
</template>
