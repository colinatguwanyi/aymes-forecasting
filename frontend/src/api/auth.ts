import api from './client'

export interface AuthUser {
  id: string
  email: string
  display_name: string | null
}

export interface AuthMeResponse {
  authenticated: boolean
  auth_mode: 'easy_auth' | 'dev'
  user: AuthUser
  roles: string[]
}

export async function fetchAuthMe(): Promise<AuthMeResponse> {
  const { data } = await api.get<AuthMeResponse>('/v1/auth/me')
  return data
}
