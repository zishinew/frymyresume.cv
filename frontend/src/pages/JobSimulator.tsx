import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { API_BASE_URL } from '../config'
import './JobSimulator.css'
import { jobs } from '../data/jobs'
import type { Job } from '../data/jobs'
import TechnicalInterview from '../components/TechnicalInterview'
// import BehavioralInterview from '../components/BehavioralInterview'
import BehavioralInterviewLive from '../components/BehavioralInterviewLive'
import LoadingScreen from '../components/LoadingScreen'

type Stage = 'intro' | 'source-selection' | 'job-selection' | 'real-job-selection' | 'resume-upload' | 'resume-screening' | 'technical' | 'technical-passed' | 'technical-failed' | 'behavioral' | 'result'

type JobSource = 'preset' | 'real'

type RealJobRow = {
  source: 'simplifyjobs_summer2026'
  category?: string
  company: string
  company_url?: string
  role: string
  location: string
  apply_url?: string
  age?: string
  details?: {
    summary?: string
    responsibilities?: string[]
    requirements?: string[]
    qualifications?: string[]
    nice_to_have?: string[]
  }
  raw?: {
    row?: string
    company_cell?: string
    role_cell?: string
    location_cell?: string
    application_cell?: string
    age_cell?: string
  }
}

type SelectedJob = (Job & { source: 'preset' }) | (Job & { source: 'real'; real?: RealJobRow })

interface ApplicationData {
  selectedJob: SelectedJob | null
  resume: File | null
}

function JobSimulator() {
  const navigate = useNavigate()
  const location = useLocation()
  const [stage, setStage] = useState<Stage>('intro')
  const [jobSource, setJobSource] = useState<JobSource | null>(null)
  const [applicationData, setApplicationData] = useState<ApplicationData>({
    selectedJob: null,
    resume: null,
  })
  const [screeningResult, setScreeningResult] = useState<any>(null)
  const [technicalScore, setTechnicalScore] = useState<number>(0)
  const [finalResult, setFinalResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [loadingText, setLoadingText] = useState<string>('')
  const [selectedType, setSelectedType] = useState<'easy' | 'medium' | 'hard' | 'all'>('all')
  const [jobDetailsRevealKey, setJobDetailsRevealKey] = useState<number>(0)
  const [showSuccessOverlay, setShowSuccessOverlay] = useState(false)
  const [showTechnicalIntro, setShowTechnicalIntro] = useState(false)

  const [realJobs, setRealJobs] = useState<RealJobRow[]>([])
  const [realJobsQuery, setRealJobsQuery] = useState<string>('')
  const [realJobsError, setRealJobsError] = useState<string>('')
  const [realJobsReloadToken, setRealJobsReloadToken] = useState<number>(0)

  const [realJobDetailsError, setRealJobDetailsError] = useState<string>('')

  const [presetTilt, setPresetTilt] = useState({ x: 0, y: 0 })
  const [realTilt, setRealTilt] = useState({ x: 0, y: 0 })

  useEffect(() => {
    if (stage === 'intro') {
      const timer = setTimeout(() => {
        setStage('source-selection')
      }, 2000)
      return () => clearTimeout(timer)
    }
  }, [stage])

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const requestedStage = params.get('stage') || params.get('test')
    if (requestedStage !== 'behavioral') return

    const company = params.get('company') || 'Test Company'
    const role = params.get('role') || 'Software Engineering Intern'

    setApplicationData({
      selectedJob: {
        id: 'behavioral-test',
        company,
        role,
        level: 'Intern',
        type: 'intern',
        difficulty: 'easy',
        description: 'Temporary behavioral interview test session',
        details: {
          about: '',
          whatYoullDo: [],
          minimumQualifications: [],
        },
        location: 'Remote',
        source: 'preset',
      },
      resume: null,
    })
    setStage('behavioral')
  }, [location.search])

  useEffect(() => {
    const load = async () => {
      if (stage !== 'real-job-selection') return
      setRealJobsError('')
      setLoading(true)
      setLoadingText('Loading real job listings...')
      try {
        const url = new URL(`${API_BASE_URL}/api/jobs/real`)
        url.searchParams.set('limit', '200')
        if (realJobsQuery.trim()) url.searchParams.set('q', realJobsQuery.trim())
        const resp = await fetch(url.toString())
        const data = await resp.json()
        if (!data?.success) throw new Error('Failed to load jobs')
        setRealJobs(Array.isArray(data.jobs) ? data.jobs : [])
      } catch (e: any) {
        console.error(e)
        setRealJobs([])
        setRealJobsError('Could not load real job listings. Is the backend running?')
      } finally {
        setLoading(false)
        setLoadingText('')
      }
    }
    void load()
  }, [stage, realJobsReloadToken])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setApplicationData({ ...applicationData, resume: e.target.files[0] })
    }
  }

  const handleJobSelect = (job: Job) => {
    setJobSource('preset')
    setApplicationData({ ...applicationData, selectedJob: { ...job, source: 'preset' } })
    setStage('resume-upload')
  }

  const handleRealJobSelect = (row: RealJobRow) => {
    const selected: SelectedJob = {
      id: `real-${encodeURIComponent(`${row.company}-${row.role}-${row.location}`)}`,
      company: row.company,
      role: row.role,
      level: 'Full-time',
      type: 'intern',
      // Placeholder; backend will infer and return effective difficulty during screening.
      difficulty: 'easy',
      description: row.category
        ? `${row.category}${row.age ? ` • ${row.age}` : ''}`
        : `Job listing${row.age ? ` • ${row.age}` : ''}`,
      details: {
        about: '',
        whatYoullDo: [],
        minimumQualifications: [],
      },
      location: row.location,
      source: 'real',
      real: row,
    }
    setJobSource('real')
    setApplicationData({ selectedJob: selected, resume: null })
    setStage('resume-upload')

    // Auto-load job description/requirements for real listings
    void (async () => {
      if (!row.apply_url) return
      let shouldAnimateReveal = false
      setRealJobDetailsError('')
      setLoading(true)
      setLoadingText('Loading job description…')
      try {
        const url = new URL(`${API_BASE_URL}/api/jobs/real/details`)
        url.searchParams.set('apply_url', row.apply_url)
        url.searchParams.set('company', row.company)
        url.searchParams.set('role', row.role)
        const resp = await fetch(url.toString())
        const data = await resp.json()
        if (!data?.success) throw new Error(data?.error || 'Failed to load job details')

        setApplicationData((prev) => {
          if (!prev.selectedJob || prev.selectedJob.source !== 'real' || prev.selectedJob.id !== selected.id || !prev.selectedJob.real) return prev
          return {
            ...prev,
            selectedJob: {
              ...prev.selectedJob,
              real: {
                ...prev.selectedJob.real,
                details: data.details || {},
              },
            },
          }
        })

        shouldAnimateReveal = true
      } catch (e: any) {
        console.error(e)
        setRealJobDetailsError('Could not load job description/requirements (posting may block scraping).')

        shouldAnimateReveal = true
      } finally {
        setLoading(false)
        setLoadingText('')

        // Trigger a keyed re-mount so the details content can animate
        if (shouldAnimateReveal) setJobDetailsRevealKey((k) => k + 1)
      }
    })()
  }

  const handleStartSimulation = async () => {
    if (!applicationData.resume || !applicationData.selectedJob) {
      alert('Please select a job and upload your resume')
      return
    }

    setLoading(true)
    setLoadingText('Screening your resume...')
    try {
      const formData = new FormData()
      formData.append('file', applicationData.resume)
      formData.append('difficulty', applicationData.selectedJob.difficulty)
      formData.append('role', applicationData.selectedJob.role)
      formData.append('level', applicationData.selectedJob.level)

      if (applicationData.selectedJob.source === 'real') {
        const r = applicationData.selectedJob.real
        formData.append('job_source', 'real')
        formData.append('company', applicationData.selectedJob.company)
        if (r?.category) formData.append('job_category', r.category)
        if (r?.location) formData.append('job_location', r.location)
        if (r?.apply_url) formData.append('job_apply_url', r.apply_url)
        if (r?.age) formData.append('job_age', r.age)
        if (r?.raw?.row) formData.append('job_row', r.raw.row)
      }

      const response = await fetch(`${API_BASE_URL}/api/screen-resume`, {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()
      setScreeningResult(data)

      // If backend inferred difficulty, persist it into the selected job
      if (data?.difficulty && (data.difficulty === 'easy' || data.difficulty === 'medium' || data.difficulty === 'hard')) {
        setApplicationData((prev) => {
          if (!prev.selectedJob) return prev
          return {
            ...prev,
            selectedJob: {
              ...prev.selectedJob,
              difficulty: data.difficulty,
            } as SelectedJob,
          }
        })
      }

      setStage('resume-screening')
      
      // Show success overlay if passed
      if (data?.passed) {
        setShowSuccessOverlay(true)
        setTimeout(() => {
          setShowSuccessOverlay(false)
        }, 2500)
      }
    } catch (error) {
      console.error('Error:', error)
      alert('An error occurred during resume screening')
    } finally {
      setLoading(false)
      setLoadingText('')
    }
  }

  const handleTechnicalComplete = (score: number) => {
    setTechnicalScore(score)

    // Check if score meets 80% threshold to proceed to behavioral
    if (score >= 80) {
      // High achievers (100%) get special screen
      if (score === 100) {
        setStage('technical-passed')
      } else {
        setStage('behavioral')
      }
    } else {
      // Score below 80% - failed to advance
      setStage('technical-failed')
    }
  }

  const buildBehavioralFeedback = (score: number, meta?: { disqualified?: boolean; flags?: any; scoring_version?: string }) => {
    if (meta?.disqualified) {
      return {
        summary: 'Your behavioral interview response included content that would disqualify a candidate in a real interview.',
        tips: [
          'Keep responses professional and workplace-appropriate.',
          'Avoid hostile, threatening, or illegal statements.',
          'Use a calm, constructive tone when discussing challenges or conflicts.'
        ]
      }
    }

    if (score >= 85) {
      return {
        summary: 'Excellent behavioral performance with clear, structured answers and strong impact.',
        tips: [
          'Keep highlighting measurable results.',
          'Maintain concise STAR structure (Situation, Task, Action, Result).'
        ]
      }
    }

    if (score >= 70) {
      return {
        summary: 'Solid behavioral answers with good clarity and relevance.',
        tips: [
          'Make your actions more explicit and detailed.',
          'Quantify outcomes where possible.'
        ]
      }
    }

    if (score >= 60) {
      return {
        summary: 'Decent effort, but responses need more structure and specificity.',
        tips: [
          'Use the STAR format to organize each answer.',
          'Include concrete examples instead of general statements.'
        ]
      }
    }

    return {
      summary: 'Behavioral responses were unclear or lacked concrete examples.',
      tips: [
        'Prepare 3–4 strong stories in advance (teamwork, conflict, leadership, challenge).',
        'Focus on what you personally did and the outcome.'
      ]
    }
  }

  const handleBehavioralComplete = async (score: number, meta?: { disqualified?: boolean; flags?: any; scoring_version?: string }) => {
    // Calculate final decision
    const resumeScore = screeningResult?.passed ? 80 : 40
    const weightedScore = (resumeScore * 0.2) + (technicalScore * 0.5) + (score * 0.3)
    
    const behavioralMinimum = 60
    const hired = (weightedScore >= 65) && (score >= behavioralMinimum) && !meta?.disqualified

    const behavioralFeedback = buildBehavioralFeedback(score, meta)
    setFinalResult({
      hired,
      weightedScore,
      resumeScore,
      technicalScore,
      behavioralScore: score,
      behavioralFeedback,
      behavioralMeta: meta
    })
    setStage('result')
  }

  const filteredJobs = selectedType === 'all'
    ? jobs
    : jobs.filter(job => job.difficulty === selectedType)

  const handleTiltMouseMove = (e: React.MouseEvent<HTMLDivElement>, setter: (tilt: { x: number; y: number }) => void) => {
    // Disable tilt effect on mobile/tablet for better performance
    if (window.innerWidth <= 768) return

    const rect = e.currentTarget.getBoundingClientRect()
    const x = (e.clientX - rect.left - rect.width / 2) / rect.width
    const y = (e.clientY - rect.top - rect.height / 2) / rect.height
    setter({ x: x * 10, y: y * 10 })
  }

  const handleTiltMouseLeave = (setter: (tilt: { x: number; y: number }) => void) => {
    setter({ x: 0, y: 0 })
  }

  const handleCardGlowMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * 100
    const y = ((e.clientY - rect.top) / rect.height) * 100
    e.currentTarget.style.setProperty('--mx', `${x}%`)
    e.currentTarget.style.setProperty('--my', `${y}%`)
  }

  const formatDifficulty = (difficulty: string) => {
    switch (difficulty) {
      case 'easy':
        return 'Easy'
      case 'medium':
        return 'Medium'
      case 'hard':
        return 'Hard'
      default:
        return difficulty
    }
  }

  const renderIntro = () => {
    return (
      <div className="intro-screen">
        <div className="intro-content">
          <h1 className="intro-title">
            Choose Your Job Listing Mode
          </h1>
          <p className="intro-subtitle">
            Select how you want to test your resume against job opportunities
          </p>
        </div>
      </div>
    )
  }

  const renderSourceSelection = () => {
    return (
      <div className="source-selection-container">
        <button
          className="home-button"
          onClick={() => navigate('/')}
          type="button"
        >
          ← Back to Home
        </button>
        <h1 className="source-selection-title">Choose Job Listings</h1>

        <div className="split-screen">
          <div
            className="split-option preset-option"
            onMouseMove={(e) => handleTiltMouseMove(e, setPresetTilt)}
            onMouseLeave={() => handleTiltMouseLeave(setPresetTilt)}
            onClick={() => {
              setJobSource('preset')
              setStage('job-selection')
            }}
            style={{
              transform: `perspective(900px) rotateX(${(-presetTilt.y).toFixed(2)}deg) rotateY(${presetTilt.x.toFixed(2)}deg)`,
            }}
            role="button"
            tabIndex={0}
          >
            <div className="split-content">
              <div className="split-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M7 7h10M7 11h10M7 15h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  <path d="M6 3h12a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3Z" stroke="currentColor" strokeWidth="2" />
                </svg>
              </div>
              <div className="split-title">Preset Jobs</div>
              <div className="split-description">Curated roles with realistic screening + interview simulations.</div>
            </div>
          </div>

          <div className="split-divider" />

          <div
            className="split-option real-option"
            onMouseMove={(e) => handleTiltMouseMove(e, setRealTilt)}
            onMouseLeave={() => handleTiltMouseLeave(setRealTilt)}
            onClick={() => {
              setJobSource('real')
              setStage('real-job-selection')
            }}
            style={{
              transform: `perspective(900px) rotateX(${(-realTilt.y).toFixed(2)}deg) rotateY(${realTilt.x.toFixed(2)}deg)`,
            }}
            role="button"
            tabIndex={0}
          >
            <div className="split-content">
              <div className="split-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M20 20H4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  <path d="M6 20V9a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v11" stroke="currentColor" strokeWidth="2" />
                  <path d="M9 7V5a3 3 0 0 1 6 0v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </div>
              <div className="split-title">Real Listings</div>
              <div className="split-description">Search real job postings and test your resume against them.</div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const renderJobSelection = () => (
    <div className="simulator-content preset-job-selection">
      <header className="simulator-header job-selection-header">
        <h1>Choose a Job</h1>
        <p className="simulator-subtitle">Pick a role, then you'll see full details and upload your resume.</p>
      </header>

      <div className="jobs-section">
        <div className="type-filter">
          <button
            className={selectedType === 'all' ? 'filter-active' : ''}
            onClick={() => setSelectedType('all')}
            type="button"
          >
            All
          </button>
          <button
            className={selectedType === 'easy' ? 'filter-active' : ''}
            onClick={() => setSelectedType('easy')}
            type="button"
          >
            Easy (Entry-level)
          </button>
          <button
            className={selectedType === 'medium' ? 'filter-active' : ''}
            onClick={() => setSelectedType('medium')}
            type="button"
          >
            Medium
          </button>
          <button
            className={selectedType === 'hard' ? 'filter-active' : ''}
            onClick={() => setSelectedType('hard')}
            type="button"
          >
            Hard (Big Tech)
          </button>
        </div>

        <div className="jobs-grid">
          {filteredJobs.map((job) => (
            <div
              key={job.id}
              className="job-card"
              onClick={() => handleJobSelect(job)}
              onMouseMove={handleCardGlowMouseMove}
              role="button"
              tabIndex={0}
            >
              <div className="job-header">
                <h3 className="job-company">{job.company}</h3>
                <div className="job-badges">
                  <span className={`job-difficulty-badge ${job.difficulty}`}>{formatDifficulty(job.difficulty)}</span>
                </div>
              </div>
              <p className="job-role">{job.role}</p>
              <p className="job-level">{job.level}</p>
              <p className="job-description">{job.description}</p>
              <p className="job-location">{job.location}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  const renderRealJobSelection = () => (
    <div className="simulator-content real-job-selection">
      <header className="simulator-header job-selection-header">
        <h1>Real Job Listings</h1>
        <p className="simulator-subtitle">Search real listings, then view details and upload your resume.</p>
      </header>

      <div className="real-jobs-toolbar">
        <div className="real-jobs-search">
          <div className="real-jobs-searchbar">
            <svg
              className="real-jobs-search-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              focusable="false"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="M20 20l-3.5-3.5" />
            </svg>
            <input
              className="real-jobs-search-input"
              type="search"
              value={realJobsQuery}
              onChange={(e) => setRealJobsQuery(e.target.value)}
              aria-label="Search real job listings"
              onKeyDown={(e) => {
                if (e.key === 'Enter') setRealJobsReloadToken((t) => t + 1)
              }}
            />
          </div>
        </div>
        <div className="real-jobs-meta">
          <div className="real-jobs-count">{realJobs.length} results</div>
          <div className="real-jobs-hint">Tip: press Enter to search</div>
        </div>
      </div>

      {realJobsError && <div className="error-message">{realJobsError}</div>}

      <div className="jobs-grid">
        {realJobs.map((row) => (
          <div
            key={`${row.company}-${row.role}-${row.location}-${row.apply_url ?? ''}`}
            className="job-card"
            onClick={() => handleRealJobSelect(row)}
            onMouseMove={handleCardGlowMouseMove}
            role="button"
            tabIndex={0}
          >
            <div className="job-header">
              <h3 className="job-company">{row.company}</h3>
            </div>
            <p className="job-role">{row.role}</p>
            <p className="job-level">{row.category || 'Job listing'}</p>
            <p className="job-description">{row.age ? `${row.age}` : 'Click to view details and apply'}</p>
            <p className="job-location">{row.location}</p>
          </div>
        ))}
      </div>
    </div>
  )

  const renderResumeUpload = () => (
    <div className="simulator-content">
      <header className="simulator-header resume-upload-header">
        <h1>Upload Your Resume</h1>
        <p className="simulator-subtitle">
          You're applying for {applicationData.selectedJob?.role} at {applicationData.selectedJob?.company}
        </p>
      </header>

      <div className="resume-upload-layout">
        <aside className="job-details-panel">
          <div className="job-details-header">
            <h2 className="job-details-role">{applicationData.selectedJob?.role}</h2>
            <div className="job-details-company">{applicationData.selectedJob?.company}</div>
            <div className="job-details-meta">
              <span className="job-detail-pill">{applicationData.selectedJob?.location}</span>
              <span className="job-detail-pill">{applicationData.selectedJob?.level}</span>
              {applicationData.selectedJob?.source === 'preset' && applicationData.selectedJob?.difficulty && (
                <span className={`job-difficulty-badge ${applicationData.selectedJob.difficulty}`}>{formatDifficulty(applicationData.selectedJob.difficulty)}</span>
              )}
            </div>
          </div>

          {applicationData.selectedJob?.source === 'real' && applicationData.selectedJob.real?.apply_url && (
            <div className="job-details-actions">
              <button
                type="button"
                className="primary-button"
                onClick={() => {
                  const job = applicationData.selectedJob
                  if (!job || job.source !== 'real' || !job.real?.apply_url) return
                  window.open(job.real.apply_url, '_blank', 'noopener,noreferrer')
                }}
                style={{ marginTop: 0 }}
              >
                Apply on company site ↗
              </button>
            </div>
          )}

          <div
            key={`job-details-${jobDetailsRevealKey}`}
            className={applicationData.selectedJob?.source === 'real' ? 'job-details-content job-details-reveal' : 'job-details-content'}
          >
            <section className="job-details-section">
              <h3 className="job-details-section-title">About the job</h3>
              <p className="job-details-text">
                {applicationData.selectedJob?.source === 'real'
                  ? (applicationData.selectedJob.real?.details?.summary
                    ? applicationData.selectedJob.real.details.summary
                    : 'This is a real listing from SimplifyJobs. Job details may be unavailable for this posting.')
                  : (applicationData.selectedJob?.details?.about || applicationData.selectedJob?.description)}
              </p>
            </section>

            {applicationData.selectedJob?.source === 'preset' && (
              <>
                {(applicationData.selectedJob.details.whatYoullDo?.length ?? 0) > 0 && (
                  <section className="job-details-section">
                    <h3 className="job-details-section-title">What you'll be doing</h3>
                    <ul className="job-details-list">
                      {applicationData.selectedJob.details.whatYoullDo.slice(0, 12).map((item, i) => (
                        <li key={`preset-do-${i}`}>{item}</li>
                      ))}
                    </ul>
                  </section>
                )}

                {(applicationData.selectedJob.details.minimumQualifications?.length ?? 0) > 0 && (
                  <section className="job-details-section">
                    <h3 className="job-details-section-title">Minimum qualifications</h3>
                    <ul className="job-details-list">
                      {applicationData.selectedJob.details.minimumQualifications.slice(0, 12).map((item, i) => (
                        <li key={`preset-min-${i}`}>{item}</li>
                      ))}
                    </ul>
                  </section>
                )}
              </>
            )}

            {applicationData.selectedJob?.source === 'real' && applicationData.selectedJob.real && (
              <>
                {realJobDetailsError && (
                  <div className="job-details-actions">
                    <div className="error-message" style={{ marginTop: 0 }}>{realJobDetailsError}</div>
                  </div>
                )}

                {(applicationData.selectedJob.real.details?.responsibilities?.length ?? 0) > 0 && (
                  <section className="job-details-section">
                    <h3 className="job-details-section-title">Responsibilities</h3>
                    <ul className="job-details-list">
                      {(applicationData.selectedJob.real.details?.responsibilities ?? []).slice(0, 12).map((r, i) => (
                        <li key={`resp-${i}`}>{r}</li>
                      ))}
                    </ul>
                  </section>
                )}

                {(applicationData.selectedJob.real.details?.requirements?.length ?? 0) > 0 && (
                  <section className="job-details-section">
                    <h3 className="job-details-section-title">Requirements</h3>
                    <ul className="job-details-list">
                      {(applicationData.selectedJob.real.details?.requirements ?? []).slice(0, 12).map((r, i) => (
                        <li key={`req-${i}`}>{r}</li>
                      ))}
                    </ul>
                  </section>
                )}
              </>
            )}
          </div>
        </aside>

        <div className="resume-upload-panel">
          <div className="resume-upload-card">
            <div className="resume-upload-section">
              <h2 className="section-title">Upload your resume</h2>
              <p className="resume-hint">PDF or TXT • Used only for this simulation</p>
              <div className="file-upload">
                <label htmlFor="resume-input" className="file-label">
                  <span className="file-icon">{applicationData.resume ? '✓' : '↑'}</span>
                  <span className="file-text">
                    {applicationData.resume ? applicationData.resume.name : 'Choose file (PDF or TXT)'}
                  </span>
                </label>
                <input
                  id="resume-input"
                  type="file"
                  accept=".pdf,.txt"
                  onChange={handleFileChange}
                  className="file-input"
                />
              </div>
            </div>

            <div className="button-group">
              <button
                onClick={handleStartSimulation}
                disabled={loading || !applicationData.resume}
                className="primary-button"
              >
                {loading ? 'Starting Simulation...' : 'Continue'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )

  const renderTechnicalPassed = () => (
    <div className="simulator-content">
      <div className="stage-indicator">
        <div className="stage-dot completed"></div>
        <div className="stage-line completed"></div>
        <div className="stage-dot completed"></div>
        <div className="stage-line"></div>
        <div className="stage-dot"></div>
      </div>

      <header className="simulator-header">
        <h1>Technical Round Complete!</h1>
        <p className="simulator-subtitle">
          Outstanding Performance
        </p>
      </header>

      <div className="result-card success">
        <div className="result-icon success">✓</div>
        <h2 className="result-title">Perfect Score - All Test Cases Passed!</h2>
        <p className="result-description">
          You've successfully solved all technical problems and passed all test cases.
          Excellent work! You're ready to proceed to the behavioral interview.
        </p>
        <div className="score-display">
          <span className="score-label">Technical Score:</span>
          <span className="score-value">{technicalScore.toFixed(1)}%</span>
        </div>
        <button
          onClick={() => setStage('behavioral')}
          className="primary-button"
        >
          Proceed to Behavioral Interview →
        </button>
      </div>
    </div>
  )

  const renderTechnicalFailed = () => (
    <div className="simulator-content">
      <div className="stage-indicator">
        <div className="stage-dot completed"></div>
        <div className="stage-line completed"></div>
        <div className="stage-dot completed"></div>
        <div className="stage-line"></div>
        <div className="stage-dot"></div>
      </div>

      <header className="simulator-header">
        <h1>Technical Round Complete</h1>
        <p className="simulator-subtitle">
          Score Below Threshold
        </p>
      </header>

      <div className="result-card">
        <div className="result-icon failure">✗</div>
        <h2 className="result-title">Score Below 80% - Unable to Proceed</h2>
        <p className="result-description">
          You need to score at least 80% on the technical interview to advance to the behavioral round.
          Your performance indicates that additional preparation may be needed.
        </p>
        <div className="score-display">
          <span className="score-label">Technical Score:</span>
          <span className="score-value">{technicalScore.toFixed(1)}%</span>
        </div>
        <div className="score-display" style={{ marginTop: '0.5rem', fontSize: '0.9rem', opacity: 0.7 }}>
          <span>Minimum Required: 80%</span>
        </div>
        <button
          onClick={() => {
            setStage('source-selection')
            setJobSource(null)
            setScreeningResult(null)
            setTechnicalScore(0)
            setApplicationData({ selectedJob: null, resume: null })
          }}
          className="secondary-button"
        >
          Try Again
        </button>
      </div>
    </div>
  )

  const parseFeedback = (feedback: string) => {
    if (!feedback) return { keyPoints: [], improvementTips: [] }
    
    const lines = feedback.split('\n')
    const keyPoints: string[] = []
    const improvementTips: string[] = []
    let currentSection = ''
    
    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.includes('KEY STRENGTHS:') || trimmed.includes('MAJOR CONCERNS:')) {
        currentSection = 'keyPoints'
        continue
      }
      if (trimmed.includes('IMPROVEMENT TIPS:')) {
        currentSection = 'tips'
        continue
      }
      if (trimmed.includes('REASONING:')) {
        currentSection = ''
        continue
      }
      if (trimmed.startsWith('-') && currentSection === 'keyPoints') {
        keyPoints.push(trimmed.substring(1).trim())
      }
      if (trimmed.startsWith('-') && currentSection === 'tips') {
        improvementTips.push(trimmed.substring(1).trim())
      }
    }
    
    return { keyPoints, improvementTips }
  }

  const renderResumeScreening = () => {
    const { keyPoints, improvementTips } = parseFeedback(screeningResult?.feedback || '')
    
    return (
      <div className="simulator-content">
        <div className="stage-indicator">
          <div className="stage-dot active"></div>
          <div className="stage-line"></div>
          <div className="stage-dot"></div>
          <div className="stage-line"></div>
          <div className="stage-dot"></div>
        </div>

        <header className="simulator-header">
          <h1>Resume Screening</h1>
          <p className="simulator-subtitle">
            Your application for {applicationData.selectedJob?.role} at {applicationData.selectedJob?.company}
          </p>
        </header>

        {showSuccessOverlay && screeningResult?.passed && (
          <div className="success-overlay">
            <div className="success-checkmark">✓</div>
            <h2 className="success-message">You got the interview!</h2>
          </div>
        )}

        <div className="result-card">
          {screeningResult?.passed ? (
            <>
              <div className="result-icon success">✓</div>
              <h2 className="result-title">Congratulations!</h2>
              <p className="result-description">You've been selected for the next round</p>
              <button
                onClick={() => {
                  setShowTechnicalIntro(true)
                  setTimeout(() => {
                    setStage('technical')
                  }, 100)
                  setTimeout(() => {
                    setShowTechnicalIntro(false)
                  }, 3000)
                }}
                className="primary-button"
              >
                Proceed to Technical Interview
              </button>
            </>
          ) : (
            <>
              <div className="result-icon failure">✗</div>
              <h2 className="result-title">Unfortunately, your application was not selected</h2>
              {keyPoints.length > 0 && (
                <div className="feedback-points">
                  <h3 className="feedback-section-title">Major Concerns</h3>
                  <ul className="feedback-list">
                    {keyPoints.map((point, idx) => (
                      <li key={idx}>{point}</li>
                    ))}
                  </ul>
                </div>
              )}
              {improvementTips.length > 0 && (
                <div className="feedback-points">
                  <h3 className="feedback-section-title">Improvement Tips</h3>
                  <ul className="feedback-list">
                    {improvementTips.map((tip, idx) => (
                      <li key={idx}>{tip}</li>
                    ))}
                  </ul>
                </div>
              )}
              <button
                onClick={() => {
                  setStage('source-selection')
                  setJobSource(null)
                  setScreeningResult(null)
                  setApplicationData({ selectedJob: null, resume: null })
                }}
                className="secondary-button"
              >
                Try Again
              </button>
            </>
          )}
        </div>
      </div>
    )
  }

  const renderTechnical = () => {
    if (!applicationData.selectedJob) return null
    
    return (
      <>
        <div className="stage-indicator" style={{ position: 'absolute', top: '1rem', left: '50%', transform: 'translateX(-50%)', zIndex: 1000 }}>
          <div className="stage-dot completed">✓</div>
          <div className="stage-line completed"></div>
          <div className="stage-dot active"></div>
          <div className="stage-line"></div>
          <div className="stage-dot"></div>
        </div>
        <TechnicalInterview
          company={applicationData.selectedJob.company}
          role={applicationData.selectedJob.role}
          difficulty={applicationData.selectedJob.difficulty}
          onComplete={handleTechnicalComplete}
        />
      </>
    )
  }

  const renderBehavioral = () => {
    if (!applicationData.selectedJob) return null
    
    return (
      <div className="simulator-content">
        <div className="stage-indicator">
          <div className="stage-dot completed">✓</div>
          <div className="stage-line completed"></div>
          <div className="stage-dot completed">✓</div>
          <div className="stage-line completed"></div>
          <div className="stage-dot active"></div>
        </div>

        <header className="simulator-header">
          <h1>Behavioral Interview</h1>
          <p className="simulator-subtitle">
            Live AI interview powered by Google Gemini - {applicationData.selectedJob.company}
          </p>
        </header>

        <BehavioralInterviewLive
          company={applicationData.selectedJob.company}
          role={applicationData.selectedJob.role}
          onComplete={handleBehavioralComplete}
        />
      </div>
    )
  }

  const renderResult = () => (
    <div className="simulator-content">
      <header className="simulator-header">
        <h1>Final Decision</h1>
      </header>

      <div className="result-card">
        {finalResult?.hired ? (
          <>
            <div className="result-icon success large">✓</div>
            <h2 className="result-title">Congratulations! You got the offer!</h2>
            <p className="result-description">
              Based on your performance across all stages, we would like to extend you an offer for the {applicationData.selectedJob?.role} position at {applicationData.selectedJob?.company}.
            </p>
            <div className="score-breakdown">
              <h3>Score Breakdown</h3>
              <p>Resume: {finalResult.resumeScore}%</p>
              <p>Technical: {finalResult.technicalScore.toFixed(1)}%</p>
              <p>Behavioral: {finalResult.behavioralScore.toFixed(1)}%</p>
              <p><strong>Overall: {finalResult.weightedScore.toFixed(1)}%</strong></p>
            </div>
            <div className="score-breakdown">
              <h3>Behavioral Feedback</h3>
              <p>{finalResult.behavioralFeedback?.summary}</p>
              <ul>
                {(finalResult.behavioralFeedback?.tips || []).map((tip: string, index: number) => (
                  <li key={`behavioral-tip-${index}`}>{tip}</li>
                ))}
              </ul>
            </div>
          </>
        ) : (
          <>
            <div className="result-icon failure large">×</div>
            <h2 className="result-title">Thank you for your interest</h2>
            <p className="result-description">
              After careful consideration, we've decided to move forward with other candidates.
            </p>
            <div className="score-breakdown">
              <h3>Score Breakdown</h3>
              <p>Resume: {finalResult.resumeScore}%</p>
              <p>Technical: {finalResult.technicalScore.toFixed(1)}%</p>
              <p>Behavioral: {finalResult.behavioralScore.toFixed(1)}%</p>
              <p><strong>Overall: {finalResult.weightedScore.toFixed(1)}%</strong></p>
            </div>
            <div className="score-breakdown">
              <h3>Behavioral Feedback</h3>
              <p>{finalResult.behavioralFeedback?.summary}</p>
              <ul>
                {(finalResult.behavioralFeedback?.tips || []).map((tip: string, index: number) => (
                  <li key={`behavioral-tip-${index}`}>{tip}</li>
                ))}
              </ul>
            </div>
          </>
        )}
        <button
          onClick={() => {
            setStage('source-selection')
            setJobSource(null)
            setScreeningResult(null)
            setFinalResult(null)
            setTechnicalScore(0)
            setApplicationData({ selectedJob: null, resume: null })
          }}
          className="primary-button"
        >
          Start New Simulation
        </button>
      </div>
    </div>
  )

  return (
    <>
      {loading && <LoadingScreen text={loadingText || undefined} />}
      {showTechnicalIntro && (
        <div className="technical-intro-overlay">
          <div className="technical-intro-content">
            <h1 className="technical-intro-title">Starting Technical Interview</h1>
          </div>
        </div>
      )}
      <div className="page">
        {stage !== 'technical' && (
          <div className="page-container">
            {stage !== 'intro' && stage !== 'source-selection' && (
              <button
                className="back-button"
                onClick={() => {
                  if (stage === 'resume-upload') {
                    if (jobSource === 'real') setStage('real-job-selection')
                    else setStage('job-selection')
                    return
                  }
                  if (stage === 'job-selection' || stage === 'real-job-selection') {
                    setStage('source-selection')
                    return
                  }
                  // default fallback
                  navigate('/')
                }}
              >
                ← {stage === 'resume-upload' ? 'Back to Jobs' : stage === 'job-selection' || stage === 'real-job-selection' ? 'Back to Mode Selection' : 'Back to Home'}
              </button>
            )}

            {stage === 'intro' && renderIntro()}
            {stage === 'source-selection' && renderSourceSelection()}
            {stage === 'job-selection' && renderJobSelection()}
            {stage === 'real-job-selection' && renderRealJobSelection()}
            {stage === 'resume-upload' && renderResumeUpload()}
            {stage === 'resume-screening' && renderResumeScreening()}
            {stage === 'technical-passed' && renderTechnicalPassed()}
            {stage === 'technical-failed' && renderTechnicalFailed()}
            {stage === 'behavioral' && renderBehavioral()}
            {stage === 'result' && renderResult()}
          </div>
        )}
        {stage === 'technical' && renderTechnical()}
      </div>
    </>
  )
}

export default JobSimulator
