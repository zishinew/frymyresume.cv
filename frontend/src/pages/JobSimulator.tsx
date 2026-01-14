import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './JobSimulator.css'
import { jobs } from '../data/jobs'
import type { Job } from '../data/jobs'
import TechnicalInterview from '../components/TechnicalInterview'
// import BehavioralInterview from '../components/BehavioralInterview'
import BehavioralInterviewLive from '../components/BehavioralInterviewLive'
import LoadingScreen from '../components/LoadingScreen'

type Stage = 'job-selection' | 'resume-upload' | 'resume-screening' | 'technical' | 'technical-passed' | 'behavioral' | 'result'

interface ApplicationData {
  selectedJob: Job | null
  resume: File | null
}

function JobSimulator() {
  const navigate = useNavigate()
  const [stage, setStage] = useState<Stage>('job-selection')
  const [applicationData, setApplicationData] = useState<ApplicationData>({
    selectedJob: null,
    resume: null,
  })
  const [screeningResult, setScreeningResult] = useState<any>(null)
  const [technicalScore, setTechnicalScore] = useState<number>(0)
  const [behavioralScore, setBehavioralScore] = useState<number>(0)
  const [finalResult, setFinalResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [selectedType, setSelectedType] = useState<'easy' | 'medium' | 'hard' | 'all'>('all')

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setApplicationData({ ...applicationData, resume: e.target.files[0] })
    }
  }

  const handleJobSelect = (job: Job) => {
    setApplicationData({ ...applicationData, selectedJob: job })
    setStage('resume-upload')
  }

  const handleStartSimulation = async () => {
    if (!applicationData.resume || !applicationData.selectedJob) {
      alert('Please select a job and upload your resume')
      return
    }

    setLoading(true)
    try {
      const formData = new FormData()
      formData.append('file', applicationData.resume)
      formData.append('difficulty', applicationData.selectedJob.difficulty)
      formData.append('role', applicationData.selectedJob.role)
      formData.append('level', applicationData.selectedJob.level)

      const response = await fetch('http://localhost:8000/api/screen-resume', {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()
      setScreeningResult(data)
      setStage('resume-screening')
    } catch (error) {
      console.error('Error:', error)
      alert('An error occurred during resume screening')
    } finally {
      setLoading(false)
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

  const handleBehavioralComplete = async (score: number) => {
    setBehavioralScore(score)
    
    // Calculate final decision
    const resumeScore = screeningResult?.passed ? 80 : 40
    const weightedScore = (resumeScore * 0.2) + (technicalScore * 0.5) + (score * 0.3)
    
    const hired = weightedScore >= 65
    
    setFinalResult({ hired, weightedScore, resumeScore, technicalScore, behavioralScore: score })
    setStage('result')
  }

  const filteredJobs = selectedType === 'all'
    ? jobs
    : jobs.filter(job => job.difficulty === selectedType)

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
                  <span className={`job-type-badge ${job.type}`}>{job.type}</span>
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
                  setStage('job-selection')
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
            setStage('job-selection')
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
      {loading && <LoadingScreen />}
      <div className="page">
        {stage !== 'technical' && (
          <div className="page-container">
            <button
              className="back-button"
              onClick={() => stage === 'resume-upload' ? setStage('job-selection') : navigate('/')}
            >
              ← {stage === 'resume-upload' ? 'Back to Jobs' : 'Back to Home'}
            </button>

            {stage === 'job-selection' && renderJobSelection()}
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
