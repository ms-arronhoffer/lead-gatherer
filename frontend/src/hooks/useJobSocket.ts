import { useEffect, useRef, useState } from 'react'
import type { JobProgressEvent } from '../types/job'

const WS_BASE = window.location.protocol === 'https:' ? 'wss:' : 'ws:'

export const useJobSocket = (jobId: string | null) => {
  const [progress, setProgress] = useState<JobProgressEvent | null>(null)
  const ws = useRef<WebSocket | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!jobId) return

    const connect = () => {
      const socket = new WebSocket(
        `${WS_BASE}//${window.location.host}/api/v1/ws/jobs/${jobId}`
      )
      socket.onmessage = (e) => {
        try {
          setProgress(JSON.parse(e.data))
        } catch {
          // ignore parse errors
        }
      }
      socket.onerror = () => {
        socket.close()
        // Fallback: poll job endpoint
        if (!pollRef.current) {
          pollRef.current = setInterval(async () => {
            try {
              const resp = await fetch(`/api/v1/jobs/${jobId}`)
              const data = await resp.json()
              setProgress({
                job_id: data.id,
                status: data.status,
                phase: data.phase,
                processed_places: data.processed_places,
                total_places: data.total_places,
                leads_found: data.leads_found,
                progress_pct: data.progress_pct,
              })
              if (['completed', 'failed', 'cancelled'].includes(data.status)) {
                clearInterval(pollRef.current!)
                pollRef.current = null
              }
            } catch {
              // ignore
            }
          }, 2000)
        }
      }
      ws.current = socket
    }

    connect()

    return () => {
      ws.current?.close()
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [jobId])

  return progress
}
