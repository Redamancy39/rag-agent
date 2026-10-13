<script setup lang="ts">
import ChatSidebar from '../../components/chat/ChatSidebar.vue'
import ChatTurnCard from '../../components/chat/ChatTurnCard.vue'
import ChatComposer from '../../components/chat/ChatComposer.vue'
import { chatThreadRef, chatTurns, fillChatQuestion } from '../../stores/chat'

const examples = [
  '菌落总数的检验方法是什么？',
  '铅的限量指标是多少？',
  '巴氏杀菌乳的微生物要求有哪些？'
]
</script>

<template>
  <section class="qa-workbench">
    <ChatSidebar />
    <section class="qa-main" :class="{ 'is-empty': !chatTurns.length }">
      <div v-show="chatTurns.length" ref="chatThreadRef" class="chat-thread" aria-live="polite">
        <ChatTurnCard v-for="turn in chatTurns" :key="turn.id" :turn="turn" />
      </div>
      <div class="chat-dock">
        <div v-if="!chatTurns.length" class="chat-start">
          <p>从当前账号可访问的已入库文档中检索。可以直接输入，或点一个示例填入。</p>
          <div class="chat-examples">
            <button v-for="example in examples" :key="example" type="button" @click="fillChatQuestion(example)">{{ example }}</button>
          </div>
        </div>
        <ChatComposer />
      </div>
    </section>
  </section>
</template>

<style>
.qa-workbench {
display: grid;
  height: calc(100dvh - 132px);
  min-height: 540px;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 16px;
}

.qa-sidebar {
display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
  min-height: 0;
  max-height: calc(100dvh - 132px);
  overflow: hidden;
  position: sticky;
  top: 20px;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-eef7ef);
  padding: 14px;
}

.qa-side-section {
display: grid;
  gap: 10px;
  min-width: 0;
}

.qa-settings {
align-content: start;
}

.qa-retrieval-settings {
max-height: 55dvh; overflow-y: auto; overscroll-behavior: contain; padding-right: 3px;
}

.qa-setting-group {
display: grid; gap: 8px; padding-bottom: 10px; border-bottom: 1px solid var(--c-d5e7dc);
}

.qa-setting-heading {
display: flex; align-items: center; justify-content: space-between; gap: 6px; width: 100%; text-align: left; background: transparent; border: 0; padding: 2px 0; color: var(--c-1f2937); cursor: pointer;
}

.qa-setting-heading > span {
display: grid; gap: 4px; min-width: 0;
}

.qa-setting-heading strong {
font-size: 13px;
}

.qa-setting-heading small {
color: var(--c-64748b); font-size: 11px; line-height: 1.5;
}

.qa-setting-heading .el-icon {
transition: transform 180ms ease; flex-shrink: 0;
}

.qa-setting-heading .rotated {
transform: rotate(90deg);
}

.qa-setting-body {
display: grid; gap: 10px; animation: qa-setting-enter 160ms ease;
}

.qa-retrieval-presets {
display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 3px; padding: 3px; border-radius: 999px; background: var(--c-e2eee7);
}

.qa-retrieval-presets button {
border: 0; border-radius: 999px; padding: 7px 0; font-size: 11px; color: var(--c-52665e); background: transparent; cursor: pointer; white-space: nowrap;
}

.qa-retrieval-presets button[aria-pressed="true"] {
background: var(--c-fff); color: var(--c-087f75); font-weight: 700; box-shadow: 0 1px 4px var(--c-173b2720);
}

.qa-retrieval-presets button:focus-visible,
.qa-setting-heading:focus-visible {
outline: 2px solid var(--c-0f766e); outline-offset: 2px;
}

.qa-setting-body input:focus-visible {
outline: 2px solid var(--c-0f766e); outline-offset: 2px;
}

.qa-slider-field {
display: grid; grid-template-columns: minmax(0, 1fr) 70px; align-items: center; gap: 7px; font-size: 12px;
}

.qa-slider-field input[type="range"],
.qa-slider-field small {
grid-column: 1 / -1; width: 100%;
}

.qa-slider-field input[type="number"] {
min-width: 0; width: 100%; box-sizing: border-box; padding: 6px 3px; border: 1px solid var(--c-cddcd3); border-radius: 6px; background: var(--c-fff); color: var(--c-334155); font: inherit;
}

.qa-slider-field input[type="range"],
.qa-check-setting input {
accent-color: var(--c-0f766e); cursor: pointer;
}

.qa-slider-field input:disabled {
opacity: .55; cursor: default;
}

.qa-slider-field small {
color: var(--c-64748b); font-size: 11px; line-height: 1.5;
}

.qa-check-setting {
display: flex; align-items: center; gap: 5px; font-size: 12px; line-height: 1.5;
}

.qa-advanced-options summary,
.qa-reset-settings {
font-size: 12px; color: var(--c-0f766e); cursor: pointer;
}

.qa-advanced-options > .qa-setting-body {
margin-top: 10px;
}

.qa-reset-settings {
justify-self: start; border: 0; background: transparent; padding: 2px 0;
}

@media (prefers-reduced-motion: reduce) {
.qa-setting-body {
animation: none;
}
}

@media (prefers-reduced-motion: reduce) {
.qa-setting-heading .el-icon {
transition: none;
}
}

.qa-history {
min-height: 0;
  grid-template-rows: auto minmax(0, 1fr);
}

.qa-history-list {
display: grid;
  align-content: start;
  gap: 2px;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: 4px;
  scrollbar-gutter: stable;
}

.qa-side-section + .qa-side-section {
border-top: 1px solid rgba(15, 118, 110, 0.16);
  padding-top: 14px;
}

.qa-side-section h2,
.qa-side-section h3 {
margin: 0;
  color: var(--c-1f2937);
  letter-spacing: 0;
}

.qa-side-section h2 {
font-size: 15px;
  font-weight: 760;
}

.qa-side-section h3 {
font-size: 14px;
  font-weight: 730;
}

.qa-side-section p {
margin: 0;
  color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.5;
}

.history-item {
display: block;
  width: 100%;
  border: 0;
  border-radius: 6px 0 0 6px;
  background: transparent;
  color: var(--c-334155);
  cursor: pointer;
  font-size: 12px;
  line-height: 1.45;
  padding: 8px 9px;
  text-align: left;
}

.history-row {
display: grid;
  grid-template-columns: minmax(0, 1fr) 30px;
  align-items: stretch;
  border-radius: 6px;
}

.history-row:hover {
background: rgba(15, 118, 110, 0.1);
}

.history-item:hover {
background: transparent;
}

.history-delete {
align-self: stretch;
  min-height: 30px;
  border-radius: 0 6px 6px 0;
  padding: 0;
  opacity: 0.58;
}

.history-row:hover .history-delete {
opacity: 1;
}

.qa-settings label {
color: var(--c-64748b);
  font-size: 12px;
}

.qa-settings .el-select {
width: 100%;
}

.retrieval-scope-hint {
margin-top: -4px !important;
  color: var(--c-0f766e) !important;
  font-size: 11px !important;
  font-weight: 650;
}

.qa-main {
display: grid;
  min-width: 0;
  min-height: 0;
  grid-template-rows: minmax(0, 1fr) auto;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-ffffff);
  overflow: hidden;
}

.qa-main.is-empty {
  grid-template-rows: 1fr auto 1fr;
}

.qa-main.is-empty .chat-dock {
  grid-row: 2;
  width: min(720px, calc(100% - 64px));
  justify-self: center;
  border: 1px solid var(--c-dce3ea);
  border-radius: 12px;
  background: var(--c-ffffff);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
  padding: 18px 18px 6px;
}

.chat-start p {
  margin: 0 0 16px;
  color: var(--c-334155);
  font-size: 15px;
  line-height: 1.75;
}

.qa-main.is-empty .chat-examples {
  justify-content: flex-start;
  margin-bottom: 14px;
}

.qa-main.is-empty .chat-composer {
  position: relative;
  width: auto;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  padding: 0 0 10px;
}

.qa-main.is-empty .chat-composer .el-textarea__inner {
  font-size: 15px;
  line-height: 1.6;
}

.qa-title {
display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--c-edf1f5);
  padding: 16px 20px 14px;
}

.qa-title h2 {
margin: 0;
  color: var(--c-111827);
  font-size: 20px;
  font-weight: 780;
  letter-spacing: 0;
}

.qa-tags {
display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.chat-thread {
display: grid;
  align-content: start;
  gap: 18px;
  min-height: 0;
  overflow: auto;
  padding: 18px 22px;
}

.chat-empty {
display: grid;
  min-height: 280px;
  align-content: center;
  justify-items: center;
  color: var(--c-64748b);
  text-align: center;
}

.chat-empty-title,
.chat-empty h3 {
margin: 0 0 8px;
  color: var(--c-111827);
  font-size: 17px;
}

.chat-examples {
display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin-top: 16px;
}

.chat-examples button {
  border: 1px solid var(--c-dce3ea);
  background: var(--c-fff);
  color: var(--c-0f766e);
  border-radius: 999px;
  padding: 8px 14px;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  cursor: pointer;
}

.chat-empty p {
max-width: 520px;
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
}

.chat-turn {
display: grid;
  gap: 14px;
}

.user-bubble,
.assistant-bubble {
display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 12px;
}

.bubble-avatar {
display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 8px;
  color: var(--c-ffffff);
  font-size: 12px;
  font-weight: 760;
}

.assistant-avatar {
background: var(--c-f59e0b);
}

.bubble-body {
border-radius: 6px;
  background: var(--c-f2f5f8);
  padding: 10px 12px;
}

.bubble-body p {
margin: 0;
  color: var(--c-111827);
  font-size: 13px;
  line-height: 1.55;
}

.bubble-body span {
display: block;
  margin-top: 6px;
  color: var(--c-64748b);
  font-size: 11px;
}

.assistant-card {
min-width: 0;
  padding: 4px 0 0;
}

.chat-progress {
display: grid;
  gap: 12px;
}

.chat-progress p {
margin: 0;
  color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.5;
}

.answer-sections {
display: grid;
  gap: 18px;
}

.answer-section {
display: grid;
  min-width: 0;
  gap: 8px;
}

.answer-section h3 {
margin: 0;
  color: var(--c-475569);
  font-size: 13px;
  font-weight: 730;
  line-height: 1.4;
}

.answer-section p {
margin: 0;
  color: var(--c-1f2937);
  font-size: 14px;
  line-height: 1.8;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.answer-basis {
border-top: 1px solid var(--c-edf1f5);
  padding-top: 14px;
}

.answer-basis p {
color: var(--c-475569);
  font-size: 13px;
}

.answer-validation {
display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.answer-validation > span {
color: var(--c-64748b);
  font-size: 12px;
}

.answer-rich-text {
display: inline;
}

.inline-citation {
margin: 0 2px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--c-0f766e);
  font: inherit;
  font-weight: 750;
  cursor: pointer;
}

.inline-citation:hover {
color: var(--c-115e59);
  text-decoration: underline;
}

.citation-chip-list {
display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.citation-chip {
max-width: 100%;
  padding: 5px 8px;
  overflow: hidden;
  border: 1px solid var(--c-b8d7d2);
  border-radius: 6px;
  background: var(--c-f0fdfa);
  color: var(--c-115e59);
  font-size: 12px;
  line-height: 1.4;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.citation-chip:hover {
border-color: var(--c-5ea99d);
  background: var(--c-e6f7f4);
}

.citation-popover {
display: grid;
  gap: 7px;
}

.citation-popover strong {
color: var(--c-111827);
  font-size: 13px;
}

.citation-popover span {
color: var(--c-64748b);
  font-size: 12px;
}

.citation-popover p {
max-height: 220px;
  margin: 0;
  overflow: auto;
  color: var(--c-334155);
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.evidence-collapse {
margin-top: 16px;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  overflow: hidden;
}

.evidence-collapse .el-collapse-item__header {
height: 40px;
  padding: 0 12px;
  background: var(--c-f8fafc);
}

.evidence-collapse .el-collapse-item__content {
padding: 12px;
}

.evidence-title {
color: var(--c-111827);
  font-size: 13px;
  font-weight: 720;
}

.evidence-table {
width: 100%;
}

.retrieval-trace-collapse {
margin-top: 10px;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  overflow: hidden;
}

.retrieval-trace-collapse .el-collapse-item__header {
height: 40px;
  padding: 0 12px;
  background: var(--c-fbfcfd);
}

.retrieval-trace-collapse .el-collapse-item__content {
padding: 12px;
}

.retrieval-trace-list {
display: grid;
  gap: 12px;
}

.live-rag-trace {
display: grid;
  gap: 8px;
  margin-top: 12px;
  padding: 10px;
  border: 1px solid var(--c-e2e8f0);
  border-radius: 8px;
  background: var(--c-f8fafc);
}

.live-rag-trace-title {
color: var(--c-111827);
  font-size: 13px;
  font-weight: 700;
}

.live-rag-trace-item {
display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: 8px;
}

.live-rag-trace-item div {
display: grid;
  gap: 2px;
  min-width: 0;
}

.live-rag-trace-item strong {
min-width: 0;
  overflow: hidden;
  color: var(--c-111827);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.live-rag-trace-item span {
color: var(--c-64748b);
  font-size: 12px;
}

.query-agent-summary {
display: grid;
  gap: 12px;
  margin-bottom: 12px;
}

.query-agent-card {
display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--c-e2e8f0);
  border-radius: 8px;
  background: var(--c-f8fafc);
}

.query-agent-card-title {
display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.query-agent-card-title strong {
color: var(--c-111827);
  font-size: 13px;
}

.query-agent-grid {
display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 8px 12px;
  color: var(--c-526172);
  font-size: 12px;
}

.query-agent-grid span {
color: var(--c-64748b);
}

.query-agent-grid p {
min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--c-111827);
}

.retrieval-trace-step {
display: grid;
  gap: 8px;
}

.retrieval-trace-head {
display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 8px;
  color: var(--c-526172);
  font-size: 12px;
}

.retrieval-trace-head strong {
min-width: 0;
  overflow: hidden;
  color: var(--c-111827);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.retrieval-score-cell {
display: grid;
  gap: 2px;
  min-width: 0;
}

.retrieval-score-cell strong {
color: var(--c-111827);
  font-size: 12px;
}

.retrieval-score-cell span {
overflow: hidden;
  color: var(--c-64748b);
  font-size: 11px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-composer {
display: grid;
  grid-template-columns: minmax(0, 1fr) 88px;
  gap: 10px;
  position: sticky;
  bottom: 0;
  z-index: 2;
  border-top: 1px solid var(--c-edf1f5);
  background: var(--c-fbfdff);
  padding: 14px 16px;
}

.query-correction-summary {
color: var(--c-008b80);
  font-size: 12px;
  overflow-wrap: anywhere;
}

@media (max-width: 1120px) {
.qa-workbench {
height: auto;
    grid-template-columns: 1fr;
}
}

@media (max-width: 1120px) {
.qa-sidebar {
grid-template-columns: repeat(3, minmax(0, 1fr));
    grid-template-rows: none;
    height: auto;
    max-height: none;
    overflow: visible;
    position: static;
}
}

@media (max-width: 1120px) {
.qa-history-list {
max-height: 240px;
}
}

@media (max-width: 1120px) {
.qa-side-section + .qa-side-section {
border-top: 0;
    padding-top: 0;
}
}

@media (max-width: 980px) {
.chat-thread {
max-height: none;
}
}

@media (max-width: 980px) {
.qa-history-list {
max-height: 220px;
}
}

@media (max-width: 760px) {
.qa-sidebar,
.chat-composer {
grid-template-columns: 1fr;
}
}

@media (max-width: 760px) {
.qa-title h2 {
font-size: 20px;
}
}
</style>
