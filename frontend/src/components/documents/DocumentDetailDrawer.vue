<script setup lang="ts">
import { detailDrawerVisible, detailTab, selectedDocument } from '../../stores/documents'
import { loadDetailTab } from '../../stores/documentDialogs'
import ChunkPreview from './ChunkPreview.vue'
import JobTimeline from './JobTimeline.vue'
import QualityReport from './QualityReport.vue'

function changeTab(name: string | number) {
  if (name === 'chunks' || name === 'jobs' || name === 'quality') void loadDetailTab(name)
}
</script>

<template>
  <el-drawer
    v-model="detailDrawerVisible"
    :title="selectedDocument ? selectedDocument.filename : '文档详情'"
    :size="'min(720px, 94vw)'"
  >
    <el-tabs :model-value="detailTab" @tab-change="changeTab">
      <el-tab-pane label="分块" name="chunks">
        <ChunkPreview v-if="detailTab === 'chunks'" />
      </el-tab-pane>
      <el-tab-pane label="处理记录" name="jobs">
        <JobTimeline v-if="detailTab === 'jobs'" />
      </el-tab-pane>
      <el-tab-pane label="质量报告" name="quality">
        <QualityReport v-if="detailTab === 'quality'" />
      </el-tab-pane>
    </el-tabs>
  </el-drawer>
</template>
