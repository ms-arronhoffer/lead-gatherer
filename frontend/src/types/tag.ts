export interface Tag {
  id: string
  name: string
  color: string | null
}

export interface TagDetail extends Tag {
  created_at: number
  updated_at: number
  lead_count: number
}

export interface TagCreate {
  name: string
  color?: string | null
}

export interface TagUpdate {
  name?: string
  color?: string | null
}
