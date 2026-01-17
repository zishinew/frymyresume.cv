import { useState, useCallback } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../services/api'

interface JobApplication {
  id: number
  company: string
  role: string
  difficulty: string
  job_source: string
  current_stage: string
}

export function useJobTracking() {
  const { isAuthenticated } = useAuth()
  const [currentJobId, setCurrentJobId] = useState<number | null>(null)
  const [isTracking, setIsTracking] = useState(false)

  const createJob = useCallback(
    async (params: {
      company: string
      role: string
      difficulty: string
      job_source?: string
      location?: string
      apply_url?: string
      category?: string
    }): Promise<number | null> => {
      if (!isAuthenticated) return null

      try {
        const response = await api.post('/api/jobs/track/create', params)
        if (response.ok) {
          const job: JobApplication = await response.json()
          setCurrentJobId(job.id)
          setIsTracking(true)
          return job.id
        }
      } catch (error) {
        console.error('Failed to create job tracking:', error)
      }
      return null
    },
    [isAuthenticated]
  )

  const updateScreening = useCallback(
    async (passed: boolean, feedback: string) => {
      if (!isAuthenticated || !currentJobId) return

      try {
        await api.post('/api/jobs/track/screening', {
          job_id: currentJobId,
          passed,
          feedback,
        })
      } catch (error) {
        console.error('Failed to update screening result:', error)
      }
    },
    [isAuthenticated, currentJobId]
  )

  const updateTechnical = useCallback(
    async (passed: boolean, score: number, details?: Record<string, unknown>) => {
      if (!isAuthenticated || !currentJobId) return

      try {
        await api.post('/api/jobs/track/technical', {
          job_id: currentJobId,
          passed,
          score,
          details,
        })
      } catch (error) {
        console.error('Failed to update technical result:', error)
      }
    },
    [isAuthenticated, currentJobId]
  )

  const updateBehavioral = useCallback(
    async (passed: boolean, score: number, feedback?: string) => {
      if (!isAuthenticated || !currentJobId) return

      try {
        await api.post('/api/jobs/track/behavioral', {
          job_id: currentJobId,
          passed,
          score,
          feedback,
        })
      } catch (error) {
        console.error('Failed to update behavioral result:', error)
      }
    },
    [isAuthenticated, currentJobId]
  )

  const finalizeJob = useCallback(
    async (hired: boolean, weightedScore: number) => {
      if (!isAuthenticated || !currentJobId) return

      try {
        await api.post('/api/jobs/track/finalize', {
          job_id: currentJobId,
          hired,
          weighted_score: weightedScore,
        })
        setIsTracking(false)
      } catch (error) {
        console.error('Failed to finalize job:', error)
      }
    },
    [isAuthenticated, currentJobId]
  )

  const resetTracking = useCallback(() => {
    setCurrentJobId(null)
    setIsTracking(false)
  }, [])

  return {
    isTracking,
    currentJobId,
    canTrack: isAuthenticated,
    createJob,
    updateScreening,
    updateTechnical,
    updateBehavioral,
    finalizeJob,
    resetTracking,
  }
}
