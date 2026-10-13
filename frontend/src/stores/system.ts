import { ref } from 'vue'
import { healthCheck } from '../api/client.ts'

export const backendOnline = ref(false)

export async function refreshBackendStatus() {
  backendOnline.value = await healthCheck()
}
