import { computed, ref } from 'vue'
import { onSessionReset } from '../auth/session'
import type { FolderScan } from '../utils/folderFiles'

export const folderScan = ref<FolderScan | null>(null)
export const folderRunning = ref(false)
export const folderStopping = ref(false)
export const folderPending = computed(() =>
  folderScan.value?.files.filter(file => file.status === 'ready' && file.selected).length || 0
)

export function resetFolderUpload() {
  folderStopping.value = true
  folderRunning.value = false
  folderScan.value = null
}

onSessionReset(resetFolderUpload)
