import { computed, ref } from 'vue'
import { ApiError, getCurrentUser } from '../api/client'
import type { UserRead } from '../types'

export const TOKEN_STORAGE_KEY = 'rag_agent_token'

export const token = ref(localStorage.getItem(TOKEN_STORAGE_KEY) || '')
export const currentUser = ref<UserRead | null>(null)
export const isLoggedIn = computed(() => Boolean(token.value && currentUser.value))
export const sessionVersion = ref(0)

const sessionResetters: Array<() => void> = []

export function onSessionReset(reset: () => void) {
  sessionResetters.push(reset)
}

let userRequest: Promise<UserRead | null> | null = null
let lastAuthFailure: 'unauthorized' | null = null

export function consumeAuthFailure(): 'unauthorized' | null {
  const failure = lastAuthFailure
  lastAuthFailure = null
  return failure
}

export function setToken(accessToken: string) {
  token.value = accessToken
  currentUser.value = null
  userRequest = null
  localStorage.setItem(TOKEN_STORAGE_KEY, accessToken)
}

export function clearSession() {
  token.value = ''
  currentUser.value = null
  userRequest = null
  sessionVersion.value += 1
  localStorage.removeItem(TOKEN_STORAGE_KEY)
  for (const reset of sessionResetters) reset()
}

export async function ensureCurrentUser(): Promise<UserRead | null> {
  if (!token.value) {
    currentUser.value = null
    return null
  }
  if (currentUser.value) return currentUser.value
  if (!userRequest) {
    const requestedToken = token.value
    const request = getCurrentUser(requestedToken)
      .then((user) => {
        if (token.value !== requestedToken) return null
        lastAuthFailure = null
        currentUser.value = user
        return user
      })
      .catch((error: unknown) => {
        if (token.value === requestedToken) {
          lastAuthFailure = error instanceof ApiError && error.status === 401 ? 'unauthorized' : null
          clearSession()
        }
        return null
      })
      .finally(() => {
        if (userRequest === request) userRequest = null
      })
    userRequest = request
  }
  return userRequest
}
