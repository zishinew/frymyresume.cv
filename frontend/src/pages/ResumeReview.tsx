import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE_URL } from '../config'
import './ResumeReview.css'
import LoadingScreen from '../components/LoadingScreen'
import CircleMeter from '../components/CircleMeter'

interface AnalysisResponse {
  success: boolean
  feedback: string
  score?: number
}

function ResumeReview() {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [jobRole, setJobRole] = useState('')
  const [loading, setLoading] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [score, setScore] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tilt, setTilt] = useState({ x: 0, y: 0 })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0]

      if (selectedFile.type === 'application/pdf' || selectedFile.type === 'text/plain') {
        setFile(selectedFile)
        setError(null)
      } else {
        setError('Please upload a PDF or TXT file')
        setFile(null)
      }
    }
  }

  const handleCardMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    // Disable tilt effect on mobile/tablet for better performance
    if (window.innerWidth <= 1024) return

    const card = e.currentTarget
    const rect = card.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const centerX = rect.width / 2
    const centerY = rect.height / 2
    const tiltX = ((y - centerY) / centerY) * -3
    const tiltY = ((x - centerX) / centerX) * 3
    setTilt({ x: tiltX, y: tiltY })
  }

  const handleCardMouseLeave = () => {
    setTilt({ x: 0, y: 0 })
  }

  const handleAnalyze = async () => {
    if (!file) {
      setError('Please upload a resume first')
      return
    }

    setLoading(true)
    setError(null)
    setFeedback(null)

    try {
      const formData = new FormData()
      formData.append('file', file)
      if (jobRole) formData.append('job_role', jobRole)

      const response = await fetch(`${API_BASE_URL}/api/analyze`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to analyze resume')
      }

      const data: AnalysisResponse = await response.json()
      setFeedback(data.feedback)
      setScore(data.score || null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  const renderMarkdown = (text: string) => {
    // Convert markdown bold **text** to <strong>
    let formatted = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    // Convert markdown italic *text* to <em>
    formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>')
    // Convert markdown code `text` to <code>
    formatted = formatted.replace(/`(.*?)`/g, '<code>$1</code>')
    return formatted
  }

  const parseFeedback = (feedback: string) => {
    if (!feedback) return { sections: [] }

    const lines = feedback.split('\n')
    const sections: Array<{ title: string; content: string[] }> = []
    let currentSection: { title: string; content: string[] } | null = null

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue

      // Skip the SCORE line as it's handled separately
      if (trimmed.toUpperCase().startsWith('SCORE:')) continue

      // Check if it's a section header (ends with : and is uppercase or title case)
      if (trimmed.endsWith(':') && trimmed.length < 50 && !trimmed.toUpperCase().startsWith('SCORE')) {
        if (currentSection) {
          sections.push(currentSection)
        }
        currentSection = {
          title: trimmed.slice(0, -1),
          content: []
        }
      } else if (currentSection) {
        if (trimmed.startsWith('-') || trimmed.startsWith('•')) {
          currentSection.content.push(trimmed.substring(1).trim())
        } else if (trimmed.length > 0) {
          currentSection.content.push(trimmed)
        }
      } else {
        // If no section yet, create a default one
        if (!currentSection) {
          currentSection = { title: 'Feedback', content: [] }
        }
        currentSection.content.push(trimmed)
      }
    }

    if (currentSection) {
      sections.push(currentSection)
    }

    return { sections }
  }

  return (
    <>
      {loading && <LoadingScreen />}
      <div className="resume-review-page">
        <div className="resume-review-container">
          <button className="back-button" onClick={() => navigate('/')}>
            ← Back to Home
          </button>

          <header className="review-header">
            <h1 className="review-title">
              Resume Review
            </h1>
            <p className="review-subtitle">
              Upload your resume and get professional AI-powered feedback
            </p>
          </header>

          {!feedback && (
            <div className="review-upload-section">
              <div 
                className="upload-card"
                onMouseMove={handleCardMouseMove}
                onMouseLeave={handleCardMouseLeave}
                style={{
                  transform: `perspective(1000px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
                  transition: 'transform 0.1s ease-out',
                }}
              >
                <label htmlFor="file-input" className="file-upload-label">
                  <div className="upload-icon-wrapper">
                    {file ? (
                      <svg className="upload-icon success" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : (
                      <svg className="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                      </svg>
                    )}
                  </div>
                  <div className="upload-content">
                    {file ? (
                      <>
                        <span className="file-name">{file.name}</span>
                        <span className="file-size">{(file.size / 1024).toFixed(1)} KB</span>
                      </>
                    ) : (
                      <>
                        <span className="upload-prompt">Click to upload or drag and drop</span>
                        <span className="upload-hint">PDF or TXT (max 10MB)</span>
                      </>
                    )}
                  </div>
                </label>
                <input
                  id="file-input"
                  type="file"
                  accept=".pdf,.txt"
                  onChange={handleFileChange}
                  className="file-input-hidden"
                />
              </div>

              <div className="job-role-section">
                <label className="job-role-label">Target Job Role</label>
                <input
                  type="text"
                  value={jobRole}
                  onChange={(e) => setJobRole(e.target.value)}
                  className="job-role-input"
                />
              </div>

              <button
                onClick={handleAnalyze}
                disabled={loading || !file}
                className="analyze-button"
              >
                {loading ? (
                  <span className="button-loading">
                    <span className="spinner"></span>
                    Analyzing...
                  </span>
                ) : (
                  'Analyze Resume'
                )}
              </button>
            </div>
          )}

          {error && (
            <div className="error-message">
              <svg className="error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <circle cx="12" cy="12" r="10" strokeWidth="2"/>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {feedback && (
            <div className="feedback-container">
              <div className="feedback-header">
                {score !== null && <CircleMeter score={score} />}
                <h2 className="feedback-title">Your Resume Analysis</h2>
                <button onClick={() => { setFeedback(null); setScore(null); setFile(null); setJobRole(''); }} className="new-analysis-button">
                  Analyze Another Resume
                </button>
              </div>
              <div className="feedback-content">
                {parseFeedback(feedback).sections.map((section, sectionIdx) => (
                  <div key={sectionIdx} className="feedback-section">
                    {section.title && section.title !== 'Feedback' && (
                      <h3 className="feedback-section-title">
                        <span className="section-number">{String(sectionIdx + 1).padStart(2, '0')}</span>
                        {section.title}
                      </h3>
                    )}
                    <div className="feedback-items">
                      {section.content.map((item, itemIdx) => (
                        <p
                          key={itemIdx}
                          className="feedback-item"
                          dangerouslySetInnerHTML={{ __html: renderMarkdown(item) }}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

export default ResumeReview
