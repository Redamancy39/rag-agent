<script setup lang="ts">
import { loadingQualityReport, selectedQualityReport } from '../../stores/documents'
import { formatReportCountMap, riskLevelLabel, riskLevelType, stageStateLabel, stageStateType, statusLabel, traceDuration, traceStateLabel, traceStateType } from '../../utils/documentStatus'
import { formatPercentScore, formatTime } from '../../utils/format'
</script>

<template>
        <div v-loading="loadingQualityReport" class="quality-report-body">
          <template v-if="selectedQualityReport">
            <section class="quality-summary-grid">
              <div class="quality-score-card">
                <span>健康分</span>
                <strong>{{ selectedQualityReport.health_score }}</strong>
              </div>
              <div>
                <span>风险等级</span>
                <strong>
                  <el-tag :type="riskLevelType(selectedQualityReport.risk_level)" effect="plain">
                    {{ riskLevelLabel(selectedQualityReport.risk_level) }}
                  </el-tag>
                </strong>
              </div>
              <div>
                <span>总分块</span>
                <strong>{{ selectedQualityReport.total_chunks }}</strong>
              </div>
              <div>
                <span>覆盖位置</span>
                <strong>{{ selectedQualityReport.unique_locations ?? selectedQualityReport.unique_pages }}</strong>
              </div>
              <div>
                <span>平均质量</span>
                <strong>{{ formatPercentScore(selectedQualityReport.average_quality_score) }}</strong>
              </div>
              <div>
                <span>低质量块</span>
                <strong>{{ selectedQualityReport.low_quality_count }}</strong>
              </div>
              <div>
                <span>OCR块</span>
                <strong>{{ selectedQualityReport.ocr_chunk_count }}</strong>
              </div>
              <div>
                <span>OCR置信度</span>
                <strong>{{ formatPercentScore(selectedQualityReport.ocr_average_score) }}</strong>
              </div>
              <div>
                <span>表格块</span>
                <strong>{{ selectedQualityReport.table_chunk_count }}</strong>
              </div>
              <div>
                <span>LLM归一化</span>
                <strong>{{ selectedQualityReport.llm_normalized_count }}</strong>
              </div>
              <div>
                <span>修复提示</span>
                <strong>{{ selectedQualityReport.preprocess_repair_count }}</strong>
              </div>
              <div>
                <span>可疑上标</span>
                <strong>{{ selectedQualityReport.suspicious_power_notation_count }}</strong>
              </div>
            </section>

            <section class="quality-section">
              <h3>处理状态</h3>
              <p>{{ selectedQualityReport.status_message || statusLabel(selectedQualityReport.status) }}</p>
              <p v-if="selectedQualityReport.latest_job_message">
                最新任务：{{ selectedQualityReport.latest_job_message }}
              </p>
              <el-progress
                v-if="selectedQualityReport.latest_job_progress_total"
                :percentage="selectedQualityReport.latest_job_progress_percent"
                :stroke-width="8"
              />
            </section>

            <section class="quality-section">
              <h3>节点追踪</h3>
              <el-timeline v-if="selectedQualityReport.latest_job_trace.length" class="job-trace-timeline compact">
                <el-timeline-item
                  v-for="item in selectedQualityReport.latest_job_trace"
                  :key="`${item.node}-${item.started_at || item.state}`"
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
                  </div>
                </el-timeline-item>
              </el-timeline>
              <p v-else>暂无节点追踪记录，重新入库后的任务会显示完整时间线。</p>
            </section>

            <section class="quality-section">
              <h3>处理阶段概览</h3>
              <div class="quality-stage-list">
                <div
                  v-for="stage in selectedQualityReport.stage_overview"
                  :key="stage.name"
                  class="quality-stage-item"
                >
                  <el-tag :type="stageStateType(stage.state)" size="small" effect="plain">
                    {{ stageStateLabel(stage.state) }}
                  </el-tag>
                  <div>
                    <strong>{{ stage.name }}</strong>
                    <p>{{ stage.detail }}</p>
                    <small v-if="stage.metric">{{ stage.metric }}</small>
                  </div>
                </div>
              </div>
            </section>

            <section class="quality-section">
              <h3>内容类型分布</h3>
              <div class="quality-pill-grid">
                <span v-for="item in formatReportCountMap(selectedQualityReport.chunk_type_counts)" :key="item.key">
                  {{ item.key }}：{{ item.count }}
                </span>
              </div>
            </section>

            <section class="quality-section">
              <h3>质量等级分布</h3>
              <div class="quality-pill-grid">
                <span v-for="item in formatReportCountMap(selectedQualityReport.quality_counts)" :key="item.key">
                  {{ item.key }}：{{ item.count }}
                </span>
              </div>
            </section>

            <section class="quality-section">
              <h3>优化建议</h3>
              <div class="quality-pill-grid quality-risk-grid">
                <span v-for="item in selectedQualityReport.risk_items" :key="item">{{ item }}</span>
              </div>
              <ul class="quality-recommendations">
                <li v-for="item in selectedQualityReport.recommendations" :key="item">{{ item }}</li>
              </ul>
            </section>
          </template>
          <el-empty v-else-if="!loadingQualityReport" description="暂无质量报告" />
        </div>
</template>
