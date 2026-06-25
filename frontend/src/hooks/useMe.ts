import { useQuery } from '@tanstack/react-query'
import { fetchMe, fetchUsers } from '../api/users'

export const useMe = () =>
  useQuery({
    queryKey: ['me'],
    queryFn: fetchMe,
    retry: false,
    staleTime: 60_000,
  })

export const useUsers = () =>
  useQuery({
    queryKey: ['users'],
    queryFn: fetchUsers,
    staleTime: 60_000,
  })
