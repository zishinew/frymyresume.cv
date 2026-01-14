import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './JobSimulator.css'
import { jobs } from '../data/jobs'
import type { Job } from '../data/jobs'
import TechnicalInterview from '../components/TechnicalInterview'
// import BehavioralInterview from '../components/BehavioralInterview'
import BehavioralInterviewLive from '../components/BehavioralInterviewLive'
import LoadingScreen from '../components/LoadingScreen'

type Stage = 'source-selection' | 'job-selection' | 'real-job-selection' | 'resume-upload' | 'resume-screening' | 'technical' | 'technical-passed' | 'behavioral' | 'result'

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
  const [stage, setStage] = useState<Stage>('source-selection')
  const [jobSource, setJobSource] = useState<JobSource | null>(null)
  const [applicationData, setApplicationData] = useState<ApplicationData>({
    selectedJob: null,
    resume: null,
  })
  const [screeningResult, setScreeningResult] = useState<any>(null)
  const [technicalScore, setTechnicalScore] = useState<number>(0)
  const [behavioralScore, setBehavioralScore] = useState<number>(0)
  const [finalResult, setFinalResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [loadingText, setLoadingText] = useState<string>('')
  const [selectedType, setSelectedType] = useState<'easy' | 'medium' | 'hard' | 'all'>('all')

  const [realJobs, setRealJobs] = useState<RealJobRow[]>([])
  const [realJobsQuery, setRealJobsQuery] = useState<string>('')
  const [realJobsError, setRealJobsError] = useState<string>('')
  const [realJobsReloadToken, setRealJobsReloadToken] = useState<number>(0)

  const [realJobDetailsLoading, setRealJobDetailsLoading] = useState<boolean>(false)
  const [realJobDetailsError, setRealJobDetailsError] = useState<string>('')

  useEffect(() => {
    const load = async () => {
      if (stage !== 'real-job-selection') return
      setRealJobsError('')
      setLoading(true)
      setLoadingText('Loading real job listings...')
      try {
        const url = new URL('http://localhost:8000/api/jobs/real')
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
      level: 'Internship',
      type: 'intern',
      // Placeholder; backend will infer and return effective difficulty during screening.
      difficulty: 'easy',
      description: `${row.category || 'Internship'}${row.age ? ` • ${row.age}` : ''}`,
      location: row.location,
      source: 'real',
      real: row,
    }
    setJobSource('real')
    setApplicationData({ selectedJob: selected, resume: null })
    setStage('resume-upload')
  }

  const loadSelectedRealJobDetails = async () => {
    const selected = applicationData.selectedJob
    if (!selected || selected.source !== 'real' || !selected.real?.apply_url) return

    setRealJobDetailsError('')
    setRealJobDetailsLoading(true)
    try {
      const url = new URL('http://localhost:8000/api/jobs/real/details')
      url.searchParams.set('apply_url', selected.real.apply_url)
      url.searchParams.set('company', selected.company)
      url.searchParams.set('role', selected.role)
      const resp = await fetch(url.toString())
      const data = await resp.json()
      if (!data?.success) throw new Error(data?.error || 'Failed to load job details')

      setApplicationData((prev) => {
        if (!prev.selectedJob || prev.selectedJob.source !== 'real' || !prev.selectedJob.real) return prev
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
    } catch (e: any) {
      console.error(e)
      setRealJobDetailsError('Could not load job description/requirements (posting may block scraping).')
    } finally {
      setRealJobDetailsLoading(false)
    }
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

      const response = await fetch('http://localhost:8000/api/screen-resume', {
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
    // Check if all questions passed (score === 100)
    if (score === 100) {
      setStage('technical-passed')
    } else {
      setStage('behavioral')
    }
  }

  const handleBehavioralComplete = async (score: number, meta?: { disqualified?: boolean; flags?: any; scoring_version?: string }) => {
    setBehavioralScore(score)
    
    // Calculate final decision
    const resumeScore = screeningResult?.passed ? 80 : 40
    const weightedScore = (resumeScore * 0.2) + (technicalScore * 0.5) + (score * 0.3)
    
    const behavioralMinimum = 60
    const hired = (weightedScore >= 65) && (score >= behavioralMinimum) && !meta?.disqualified
    
    setFinalResult({ hired, weightedScore, resumeScore, technicalScore, behavioralScore: score })
    setStage('result')
  }

  const filteredJobs = selectedType === 'all'
    ? jobs
    : jobs.filter(job => job.difficulty === selectedType)

  const renderSourceSelection = () => (
    <div className="simulator-content">
      <header className="simulator-header">
        <h1>Choose Job Listings</h1>
        <p className="simulator-subtitle">Use preset jobs or pull real internship listings.</p>
      </header>

      <div className="result-card" style={{ maxWidth: 820, margin: '0 auto' }}>
        <h2 className="result-title" style={{ marginBottom: '0.5rem' }}>How do you want to pick jobs?</h2>
        <p className="result-description" style={{ marginBottom: '1.5rem' }}>
          Preset jobs are curated. Real jobs come from SimplifyJobs/Summer2026-Internships.
        </p>

        <div className="button-group" style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
          <button
            className="primary-button"
            onClick={() => {
              setJobSource('preset')
              setStage('job-selection')
            }}
          >
            Use Preset Jobs
          </button>
          <button
            className="secondary-button"
            onClick={() => {
              setJobSource('real')
              setStage('real-job-selection')
            }}
          >
            Use Real Job Listings
          </button>
        </div>
      </div>
    </div>
  )

  const renderRealJobSelection = () => (
    <div className="simulator-content">
      <header className="simulator-header">
        <h1>Real Job Listings</h1>
        <p className="simulator-subtitle">
          Powered by SimplifyJobs/Summer2026-Internships (shows all fields provided in the repo list).
        </p>
      </header>

      <div className="result-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            value={realJobsQuery}
            onChange={(e) => setRealJobsQuery(e.target.value)}
            placeholder="Search company, role, location..."
            style={{
              flex: 1,
              minWidth: 260,
              padding: '0.75rem 1rem',
              borderRadius: 10,
              border: '1px solid var(--border-color)',
              background: 'var(--card-bg-solid)',
              color: 'var(--text-primary)',
            }}
          />
          <button
            className="primary-button"
            onClick={() => {
              setRealJobsReloadToken((t) => t + 1)
            }}
          >
            Search
          </button>
        </div>
        {realJobsError && (
          <div className="error-message" style={{ marginTop: '1rem' }}>{realJobsError}</div>
        )}
      </div>

      <div className="jobs-grid">
        {realJobs.map((row, idx) => (
          <div
            key={`${row.company}-${row.role}-${row.location}-${idx}`}
            className="job-card"
            onClick={() => handleRealJobSelect(row)}
            style={{ cursor: 'pointer' }}
          >
            <div className="job-header">
              <h3 className="job-company">{row.company}</h3>
            </div>
            <p className="job-role">{row.role}</p>
            <p className="job-description">{row.category || 'Internship'}</p>
            <p className="job-location">{row.location}{row.age ? ` • ${row.age}` : ''}</p>
            {row.apply_url && (
              <div style={{ marginTop: '0.5rem' }}>
                <button
                  type="button"
                  className="job-apply-button"
                  onClick={(e) => {
                    e.stopPropagation()
                    handleRealJobSelect(row)
                  }}
                >
                  View in simulator
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )

  const renderJobSelection = () => (
    <div className="simulator-content">
      <header className="simulator-header">
        <h1>Job Application Simulator</h1>
        <p className="simulator-subtitle">
          Select a position to apply for and experience the full interview process
        </p>
      </header>

      <div className="job-selection">
        <div className="type-filter">
          <button
            className={selectedType === 'all' ? 'filter-active' : ''}
            onClick={() => setSelectedType('all')}
          >
            All Jobs
          </button>
          <button
            className={selectedType === 'easy' ? 'filter-active' : ''}
            onClick={() => setSelectedType('easy')}
          >
            Easy (Startups)
          </button>
          <button
            className={selectedType === 'medium' ? 'filter-active' : ''}
            onClick={() => setSelectedType('medium')}
          >
            Medium
          </button>
          <button
            className={selectedType === 'hard' ? 'filter-active' : ''}
            onClick={() => setSelectedType('hard')}
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
            >
              <div className="job-header">
                <h3 className="job-company">{job.company}</h3>
                <div className="job-badges">
                  <span className={`job-difficulty-badge ${job.difficulty}`}>{job.difficulty}</span>
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

  const renderResumeUpload = () => (
    <div className="simulator-content">
      <header className="simulator-header">
        <h1>Upload Your Resume</h1>
        <p className="simulator-subtitle">
          You're applying for {applicationData.selectedJob?.role} at {applicationData.selectedJob?.company}
        </p>
      </header>

      <div className="resume-upload-card">
        <div className="selected-job-summary">
          <h3>{applicationData.selectedJob?.company}</h3>
          <p>{applicationData.selectedJob?.role}</p>
          <span className={`job-type-badge ${applicationData.selectedJob?.type}`}>
            {applicationData.selectedJob?.type}
          </span>
        </div>

        {applicationData.selectedJob?.source === 'real' && applicationData.selectedJob.real && (
          <div style={{
            marginTop: '1rem',
            padding: '1rem',
            borderRadius: 12,
            border: '1px solid var(--border-color)',
            background: 'var(--card-bg-solid)'
          }}>
            <h4 style={{ margin: 0, marginBottom: '0.5rem', color: 'var(--text-primary)' }}>Listing details</h4>
            <p style={{ margin: 0, color: 'var(--text-secondary)' }}><strong>Category:</strong> {applicationData.selectedJob.real.category || '—'}</p>
            <p style={{ margin: 0, color: 'var(--text-secondary)' }}><strong>Location:</strong> {applicationData.selectedJob.real.location || '—'}</p>
            <p style={{ margin: 0, color: 'var(--text-secondary)' }}><strong>Age:</strong> {applicationData.selectedJob.real.age || '—'}</p>
            {applicationData.selectedJob.real.apply_url && (
              <div style={{ marginTop: '0.5rem' }}>
                <button
                  type="button"
                  className="job-apply-button"
                  onClick={() => {
                    const url = applicationData.selectedJob?.real?.apply_url
                    if (!url) return
                    window.open(url, '_blank', 'noopener,noreferrer')
                  }}
                >
                  Open original application
                </button>
              </div>
            )}

            {applicationData.selectedJob.real.apply_url && (
              <div style={{ marginTop: '0.75rem' }}>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={loadSelectedRealJobDetails}
                  disabled={realJobDetailsLoading}
                  style={{ marginTop: 0 }}
                >
                  {realJobDetailsLoading ? 'Loading job details…' : 'Load job description & requirements'}
                </button>
                {realJobDetailsError && (
                  <div className="error-message" style={{ marginTop: '0.5rem' }}>{realJobDetailsError}</div>
                )}
              </div>
            )}

            {applicationData.selectedJob.real.details && (
              <div style={{ marginTop: '0.75rem' }}>
                {applicationData.selectedJob.real.details.summary && (
                  <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
                    <strong>Description:</strong> {applicationData.selectedJob.real.details.summary}
                  </p>
                )}

                {(applicationData.selectedJob.real.details.requirements?.length ?? 0) > 0 && (
                  <details style={{ marginTop: '0.75rem' }}>
                    <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)' }}>Requirements</summary>
                    <ul style={{ marginTop: '0.5rem', color: 'var(--text-secondary)' }}>
                      {(applicationData.selectedJob.real.details.requirements ?? []).map((r, i) => (
                        <li key={`req-${i}`}>{r}</li>
                      ))}
                    </ul>
                  </details>
                )}

                {(applicationData.selectedJob.real.details.qualifications?.length ?? 0) > 0 && (
                  <details style={{ marginTop: '0.75rem' }}>
                    <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)' }}>Qualifications</summary>
                    <ul style={{ marginTop: '0.5rem', color: 'var(--text-secondary)' }}>
                      {(applicationData.selectedJob.real.details.qualifications ?? []).map((r, i) => (
                        <li key={`qual-${i}`}>{r}</li>
                      ))}
                    </ul>
                  </details>
                )}

                {(applicationData.selectedJob.real.details.responsibilities?.length ?? 0) > 0 && (
                  <details style={{ marginTop: '0.75rem' }}>
                    <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)' }}>Responsibilities</summary>
                    <ul style={{ marginTop: '0.5rem', color: 'var(--text-secondary)' }}>
                      {(applicationData.selectedJob.real.details.responsibilities ?? []).map((r, i) => (
                        <li key={`resp-${i}`}>{r}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )}
            {applicationData.selectedJob.real.raw?.row && (
              <details style={{ marginTop: '0.75rem' }}>
                <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)' }}>Raw source row</summary>
                <pre style={{
                  marginTop: '0.5rem',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  padding: '0.75rem',
                  borderRadius: 10,
                  border: '1px solid var(--border-color)',
                  background: 'var(--bg-primary)',
                  color: 'var(--text-secondary)'
                }}>{applicationData.selectedJob.real.raw.row}</pre>
              </details>
            )}
          </div>
        )}

        <div className="resume-upload-section">
          <h2 className="section-title">Upload Your Resume</h2>
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
            {loading ? 'Starting Simulation...' : 'Apply Now!'}
          </button>
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

        <div className="result-card">
          {screeningResult?.passed ? (
            <>
              <div className="result-icon success">✓</div>
              <h2 className="result-title">Congratulations!</h2>
              <p className="result-description">You've been selected for the next round</p>
              <button
                onClick={() => setStage('technical')}
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
          </>
        )}
        <button
          onClick={() => {
            setStage('source-selection')
            setJobSource(null)
            setScreeningResult(null)
            setFinalResult(null)
            setTechnicalScore(0)
            setBehavioralScore(0)
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
      <div className="page">
        {stage !== 'technical' && (
          <div className="page-container">
            <button
              className="back-button"
              onClick={() => {
                if (stage === 'resume-upload') {
                  if (jobSource === 'real') setStage('real-job-selection')
                  else setStage('job-selection')
                  return
                }
                if (stage === 'job-selection' || stage === 'real-job-selection' || stage === 'source-selection') {
                  navigate('/')
                  return
                }
                // default fallback
                navigate('/')
              }}
            >
              ← {stage === 'resume-upload' ? 'Back to Jobs' : 'Back to Home'}
            </button>

            {stage === 'source-selection' && renderSourceSelection()}
            {stage === 'job-selection' && renderJobSelection()}
            {stage === 'real-job-selection' && renderRealJobSelection()}
            {stage === 'resume-upload' && renderResumeUpload()}
            {stage === 'resume-screening' && renderResumeScreening()}
            {stage === 'technical-passed' && renderTechnicalPassed()}
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
