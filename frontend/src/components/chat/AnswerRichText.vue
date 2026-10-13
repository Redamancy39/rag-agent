<script setup lang="ts">
import type { ChatResponse } from '../../types'
import { answerTextSegments } from '../../utils/chatResponse'
import CitationPopover from './CitationPopover.vue'

defineProps<{ text: string; response: ChatResponse; turnId: string; part: string }>()
</script>

<template>
  <p class="answer-rich-text">
    <template v-for="(segment, segmentIndex) in answerTextSegments(text)" :key="`${turnId}-${part}-${segmentIndex}`">
      <span v-if="segment.citationId === null">{{ segment.text }}</span>
      <CitationPopover v-else :response="response" :citation-id="segment.citationId" :label="segment.text" />
    </template>
  </p>
</template>
