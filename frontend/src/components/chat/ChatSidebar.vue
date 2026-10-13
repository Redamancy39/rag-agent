<script setup lang="ts">
import { Delete } from '@element-plus/icons-vue'
import ChatRetrievalSettings from '../ChatRetrievalSettings.vue'
import { chatHistory, clearConversation, deleteHistoryTurn, deletingChatLogId, effectiveChatDocumentIds, loadingChatHistory, retrievalPreferences, selectedChatDocumentIds, selectedCollectionDocumentIds, showHistoryTurn } from '../../stores/chat'
import { currentUser } from '../../auth/session'
import { documentCollections, indexedDocuments, loadingDocumentCollections, selectedChatCollectionIds } from '../../stores/documents'
</script>

<template>
<aside class="qa-sidebar">
          <section class="qa-side-section">
            <p>按当前账号权限检索已入库文档</p>
            <el-button type="primary" plain @click="clearConversation">新建对话</el-button>
          </section>

          <ChatRetrievalSettings :key="currentUser?.id" v-model="retrievalPreferences"
            :scope-summary="selectedChatCollectionIds.length || selectedChatDocumentIds.length ? `${effectiveChatDocumentIds.length} 个已入库文档` : '全部可访问文档'">
            <template #scope>
            <label>检索文档集</label>
            <el-select
              v-model="selectedChatCollectionIds"
              multiple
              collapse-tags
              collapse-tags-tooltip
              clearable
              filterable
              :loading="loadingDocumentCollections"
              placeholder="全部可访问文档"
            >
              <el-option
                v-for="collection in documentCollections"
                :key="collection.id"
                :label="`${collection.name}（${collection.document_count}）`"
                :value="collection.id"
              />
            </el-select>
            <p v-if="selectedChatCollectionIds.length" class="retrieval-scope-hint">
              已从文档集选中 {{ selectedCollectionDocumentIds.length }} 个已入库文档
            </p>
            <label>指定文档（可选）</label>
            <el-select
              v-model="selectedChatDocumentIds"
              multiple
              collapse-tags
              collapse-tags-tooltip
              clearable
              filterable
              placeholder="选择额外文档"
            >
              <el-option
                v-for="document in indexedDocuments"
                :key="document.id"
                :label="document.filename"
                :value="document.id"
              />
            </el-select>
            <div class="setting-row">
              <span>检索范围</span>
              <strong>
                {{
                  selectedChatCollectionIds.length || selectedChatDocumentIds.length
                    ? `${effectiveChatDocumentIds.length} 个文档`
                    : '全部可访问文档'
                }}
              </strong>
            </div>
            <p>与所选文档集共同参与检索；只选择文档时，仅检索这些文档。</p>
            <div class="setting-row">
              <span>输出格式</span>
              <strong>结论 · 依据</strong>
            </div>
            </template>
          </ChatRetrievalSettings>

          <section class="qa-side-section qa-history">
            <h3>历史记录</h3>
            <p v-if="loadingChatHistory" class="muted">正在加载历史记录...</p>
            <div v-else class="qa-history-list">
              <div
                v-for="turn in chatHistory"
                :key="turn.id"
                class="history-row"
              >
                <button class="history-item" type="button" @click="showHistoryTurn(turn)">
                  {{ turn.question }}
                </button>
                <el-button
                  class="history-delete"
                  text
                  size="small"
                  type="danger"
                  :icon="Delete"
                  :loading="deletingChatLogId === turn.logId"
                  :aria-label="`删除问答记录：${turn.question}`"
                  @click.stop="deleteHistoryTurn(turn)"
                />
              </div>
              <p v-if="!chatHistory.length" class="muted">暂无历史问题</p>
            </div>
          </section>
</aside>
</template>
