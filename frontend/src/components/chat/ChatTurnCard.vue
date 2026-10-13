<script setup lang="ts">
import AnswerRichText from './AnswerRichText.vue'
import CitationPopover from './CitationPopover.vue'
import EvidenceTable from './EvidenceTable.vue'
import RetrievalTracePanel from './RetrievalTracePanel.vue'
import { answerBasisText, chatStageLabel, citationValidationLabel, citationValidationType, documentScopeLabel, getAnswerSections, getRetrievalTrace, jobTraceMessage, jobTraceMeta, jobTraceStage, legacyCitationNote } from '../../utils/chatResponse'
import { chatJobTraceItems } from '../../stores/chat'
import type { ChatTurn } from '../../types'
defineProps<{ turn: ChatTurn }>()
</script>

<template>
            <article class="chat-turn">
              <div class="user-bubble">
                <div class="bubble-avatar user-avatar">问</div>
                <div class="bubble-body">
                  <p>{{ turn.question }}</p>
                  <span>{{ documentScopeLabel(turn) }} · {{ turn.createdAt }}</span>
                </div>
              </div>

              <div class="assistant-bubble">
                <div class="bubble-avatar assistant-avatar">答</div>
                <div class="assistant-card">
                  <div v-if="turn.loading" class="chat-progress" aria-live="polite">
                    <el-skeleton :rows="4" animated />
                    <el-progress :percentage="turn.progress" :stroke-width="8" />
                    <p>{{ turn.progressMessage }}</p>
                    <div v-if="chatJobTraceItems(turn).length" class="live-rag-trace">
                      <div class="live-rag-trace-title">RAG 执行过程</div>
                      <article
                        v-for="(item, index) in chatJobTraceItems(turn)"
                        :key="`${turn.id}-live-${index}-${jobTraceStage(item)}`"
                        class="live-rag-trace-item"
                      >
                        <el-tag size="small" effect="plain">
                          {{ chatStageLabel(jobTraceStage(item)) }}
                        </el-tag>
                        <div>
                          <strong>{{ jobTraceMessage(item) }}</strong>
                          <span>{{ jobTraceMeta(item) }}</span>
                        </div>
                      </article>
                    </div>
                  </div>
                  <el-alert v-else-if="turn.error" type="error" :title="turn.error" show-icon :closable="false" />

                  <template v-else-if="turn.response">
                    <div class="answer-validation">
                      <el-tag v-if="turn.response.retrieval_only" size="small" effect="plain" type="info">
                        检索证据模式
                      </el-tag>
                      <el-tag
                        size="small"
                        effect="plain"
                        :type="citationValidationType(turn.response)"
                      >
                        {{ citationValidationLabel(turn.response) }}
                      </el-tag>
                      <span v-if="turn.response.knowledge_search === false && turn.response.knowledge_search_reason" class="query-correction-summary">
                        {{ turn.response.knowledge_search_reason }}
                      </span>
                      <span v-if="turn.response.query_plan?.corrections?.length" class="query-correction-summary">
                        本次纠错：{{ turn.response.query_plan.corrections.map(item => `${item.original} → ${item.replacement}`).join('；') }}
                      </span>
                    </div>
                    <div class="answer-sections">
                      <section class="answer-section answer-conclusion">
                        <h3>结论</h3>
                        <AnswerRichText :text="getAnswerSections(turn.response).conclusion" :response="turn.response" :turn-id="turn.id" part="conclusion" />
                      </section>
                      <section class="answer-section answer-basis">
                        <h3>依据</h3>
                        <AnswerRichText :text="answerBasisText(turn.response)" :response="turn.response" :turn-id="turn.id" part="basis" />
                        <div v-if="turn.response.citations.length" class="citation-chip-list">
                          <CitationPopover
                            v-for="(citation, citationIndex) in turn.response.citations"
                            :key="citation.chunk_id || `${turn.id}-citation-${citationIndex}`"
                            chip
                            :citation="citation"
                            :index="citationIndex"
                          />
                        </div>
                        <p v-else-if="legacyCitationNote(turn.response)" class="source-note">{{ legacyCitationNote(turn.response) }}</p>
                      </section>
                    </div>

                    <EvidenceTable v-if="turn.response.knowledge_search !== false" :response="turn.response" :turn-id="turn.id" />

                    <RetrievalTracePanel v-if="getRetrievalTrace(turn.response).length" :response="turn.response" :turn-id="turn.id" />
                  </template>
                </div>
              </div>
            </article>
</template>
