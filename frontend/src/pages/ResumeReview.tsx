import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
      if (notes) formData.append('notes', notes)

      const response = await fetch('http://localhost:8000/api/analyze', {
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
      <div className="page">
        <div className="page-container">
          <button className="back-button" onClick={() => navigate('/')}>
            ← Back to Home
          </button>

          <header className="page-header" style={{ textAlign: 'center' }}>
            <h1>Resume Review</h1>
            <p className="page-subtitle">
              Upload your resume and get professional AI-powered feedback
            </p>
          </header>

          {!feedback && (
            <div className="upload-section">
              <div className="file-upload">
                <label htmlFor="file-input" className="file-label">
                  <div className="upload-icon">
                    {file ? '✓' : '↑'}
                  </div>
                  <div className="upload-text">
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
                  className="file-input"
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '2rem' }}>
                <div className="input-group" style={{ width: '100%', maxWidth: '400px' }}>
                  <label className="input-label" style={{ textAlign: 'center' }}>Target Job Role</label>
                  <input
                    type="text"
                    placeholder="Software Engineer"
                    value={jobRole}
                    onChange={(e) => setJobRole(e.target.value)}
                    className="text-input"
                  />
                </div>
              </div>

              <button
                onClick={handleAnalyze}
                disabled={loading || !file}
                className="analyze-button apply-button"
              >
                {loading ? 'Analyzing...' : 'Apply!'}
              </button>
            </div>
          )}

          {error && (
            <div className="error-message">
              <span className="error-icon">!</span>
              {error}
            </div>
          )}

          {feedback && (
            <div className="feedback-container">
              {score !== null && <CircleMeter score={score} />}
              <h2 className="feedback-title">Feedback</h2>
              <div className="feedback-content">
                {parseFeedback(feedback).sections.map((section, sectionIdx) => (
                  <div key={sectionIdx} className="feedback-section">
                    {section.title && section.title !== 'Feedback' && (
                      <h3 className="feedback-section-title">{section.title}</h3>
                    )}
                    {section.content.map((item, itemIdx) => (
                      <p
                        key={itemIdx}
                        className="feedback-item"
                        dangerouslySetInnerHTML={{ __html: renderMarkdown(item) }}
                      />
                    ))}
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
