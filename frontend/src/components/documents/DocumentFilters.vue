<script setup lang="ts">
import { changeDocumentFilter, documentCollectionFilter, documentCollections, documentLlmFilter, documentQuery, documentStatusFilter, documentTypeFilter, documents, filteredDocuments } from '../../stores/documents'
</script>

<template>
          <div class="document-filter-toolbar">
            <el-input v-model="documentQuery" aria-label="搜索文档文件名" class="document-name-search" placeholder="搜索文件名" clearable @input="changeDocumentFilter" />
            <div class="document-filter-field">
            <label for="document-collection-filter">文档集</label>
            <el-select id="document-collection-filter" v-model="documentCollectionFilter" filterable @change="changeDocumentFilter">
              <el-option label="全部可访问文档" value="all" />
              <el-option label="未分组" value="unassigned" />
              <el-option v-for="collection in documentCollections" :key="collection.id" :label="collection.name" :value="collection.id" />
            </el-select>
            </div>
            <div class="document-filter-field">
            <label for="document-llm-filter">LLM 状态</label>
            <el-select id="document-llm-filter" v-model="documentLlmFilter" class="llm-status-filter" @change="changeDocumentFilter">
              <el-option label="全部状态" value="all" />
              <el-option label="已有 LLM 检测结果" value="checked" />
              <el-option label="已有大模型整理结果" value="normalized" />
              <el-option label="未调用 LLM" value="not_run" />
              <el-option label="检测或入库异常" value="failed" />
              <el-option label="历史记录不足" value="unknown" />
              <el-option label="检测中" value="running" />
            </el-select>
            </div>
            <div class="document-filter-field">
            <label for="document-status-filter">入库状态</label>
            <el-select id="document-status-filter" v-model="documentStatusFilter" class="document-state-filter" @change="changeDocumentFilter">
              <el-option label="全部" value="all" />
              <el-option label="已入库" value="indexed" />
              <el-option label="排队或处理中" value="processing" />
              <el-option label="失败" value="failed" />
            </el-select>
            </div>
            <div class="document-filter-field">
            <label for="document-type-filter">格式</label>
            <el-select id="document-type-filter" v-model="documentTypeFilter" class="document-state-filter" @change="changeDocumentFilter">
              <el-option label="全部格式" value="all" />
              <el-option v-for="type in ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'md', 'markdown', 'txt']" :key="type" :label="type.toUpperCase()" :value="type" />
            </el-select>
            </div>
            <span>共 {{ documents.length }} 个可访问文档 · 筛选结果 {{ filteredDocuments.length }} 个</span>
          </div>
</template>
