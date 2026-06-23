import { create } from 'zustand'

interface ActiveJobStore {
  activeJobId: string | null
  setActiveJobId: (id: string | null) => void
}

export const useActiveJobStore = create<ActiveJobStore>((set) => ({
  activeJobId: null,
  setActiveJobId: (id) => set({ activeJobId: id }),
}))
