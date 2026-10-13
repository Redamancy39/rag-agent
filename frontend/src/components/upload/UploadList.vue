<script setup lang="ts">
import { Delete, Loading } from '@element-plus/icons-vue'
import { removeUploadItem, uploadItems } from '../../stores/uploadQueue'
import { uploadProgressMeta, uploadStatusType } from '../../utils/documentStatus'
</script>

<template>
            <div v-if="uploadItems.length" class="upload-list">
              <div v-for="item in uploadItems" :key="item.id" class="upload-row">
                <div class="upload-row-main">
                  <strong :title="item.relativePath || item.filename">{{ item.relativePath || item.filename }}</strong>
                  <div class="upload-row-status">
                    <span>{{ item.message }}</span>
                    <small v-if="uploadProgressMeta(item)">{{ uploadProgressMeta(item) }}</small>
                  </div>
                  <el-button size="small" text :icon="Delete" @click="removeUploadItem(item.id)">
                    清除
                  </el-button>
                </div>
                <div v-if="item.status === 'indexing' && !item.progressTotal" class="upload-stage-waiting" role="status">
                  <el-icon class="is-loading"><Loading /></el-icon>
                  <span>{{ item.stageLabel || '后台处理中' }}</span>
                </div>
                <el-progress v-else
                  :percentage="item.progress"
                  :status="uploadStatusType(item.status)"
                  :stroke-width="8"
                />
              </div>
            </div>
</template>
