import client from './client'
import type { User } from '../types/user'

export async function fetchMe(): Promise<User> {
  const { data } = await client.get<User>('/me')
  return data
}

export async function fetchUsers(): Promise<User[]> {
  const { data } = await client.get<User[]>('/users')
  return data
}
