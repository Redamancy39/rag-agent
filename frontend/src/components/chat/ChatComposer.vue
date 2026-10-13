<script setup lang="ts">
import QueryAssistance from '../QueryAssistance.vue'
import { currentUser, token } from '../../auth/session'
import { chatQuestion, loadingChat, submitChat } from '../../stores/chat'

function onEnter(event: KeyboardEvent) {
  if (event.isComposing || event.shiftKey) return
  event.preventDefault()
  void submitChat()
}
</script>

<template>
  <footer class="chat-composer">
    <QueryAssistance :key="currentUser?.id" v-model:question="chatQuestion" :token="token" />
    <el-input
      v-model="chatQuestion"
      type="textarea"
      :autosize="{ minRows: 1, maxRows: 6 }"
      :maxlength="4000"
      aria-label="输入问题"
      placeholder="输入食品安全国家标准相关问题，Enter 发送，Shift+Enter 换行"
      @keydown.enter="onEnter"
    />
    <el-button type="primary" :loading="loadingChat" @click="submitChat">发送</el-button>
  </footer>
</template>
