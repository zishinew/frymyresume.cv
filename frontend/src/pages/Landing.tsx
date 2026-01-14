import { useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import './Landing.css'

function Landing() {
  const navigate = useNavigate()
  const [isLoaded, setIsLoaded] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsLoaded(true)
    }, 100)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="landing" style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <div className="landing-split">
        {/* Left Side - Content */}
        <div className={`landing-left ${isLoaded ? 'loaded' : ''}`}>
          <div className="landing-content">
            <div className="brand-section">
              <h1 className="brand-title">frymyresume.cv</h1>
              <p className="brand-tagline">
                Test the potential of your resume with AI-powered feedback and a full internship interview pipeline.
              </p>
            </div>

            <div className="features-list">
              <div className="feature-item">
                <div className="feature-number">01</div>
                <div className="feature-info">
                  <h3>Resume Review</h3>
                  <p>Get instant AI-powered feedback on your resume</p>
                </div>
              </div>

              <div className="feature-item">
                <div className="feature-number">02</div>
                <div className="feature-info">
                  <h3>Full Interview Pipeline</h3>
                  <p>Experience realistic internship screening, technical, and behavioral rounds</p>
                </div>
              </div>

              <div className="feature-item">
                <div className="feature-number">03</div>
                <div className="feature-info">
                  <h3>Internship Preparation</h3>
                  <p>Practice for top internship programs across tech and finance</p>
                </div>
              </div>
            </div>

            <div className="cta-buttons">
              <button
                className="cta-primary"
                onClick={() => navigate('/job-simulator')}
              >
                Test Your Resume Against Jobs!
              </button>
              <button
                className="cta-secondary"
                onClick={() => navigate('/resume-review')}
              >
                Review Resume
              </button>
            </div>

            <div className="landing-stats">
              <div className="stat">
                <span className="stat-value">AI-Powered</span>
                <span className="stat-label">Realistic Feedback</span>
              </div>
              <div className="stat">
                <span className="stat-value">Full Pipeline</span>
                <span className="stat-label">End-to-End Experience</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right Side - Demo Video */}
        <div className={`landing-right ${isLoaded ? 'loaded' : ''}`}>
          <div className="demo-container">
            <div className="demo-video">
              <div className="video-placeholder">
                <div className="play-button">
                  <svg width="60" height="60" viewBox="0 0 60 60" fill="none">
                    <circle cx="30" cy="30" r="30" fill="rgba(17, 17, 17, 0.8)" />
                    <path d="M24 18L42 30L24 42V18Z" fill="white" />
                  </svg>
                </div>
                <div className="placeholder-text">Demo Video Coming Soon</div>
              </div>
            </div>

            <div className="floating-cards">
              <div className="floating-card card-1">
                <div className="card-icon">✓</div>
                <div className="card-text">Resume Passed</div>
              </div>
              <div className="floating-card card-2">
                <div className="card-icon">→</div>
                <div className="card-text">Technical Round</div>
              </div>
              <div className="floating-card card-3">
                <div className="card-icon">✓</div>
                <div className="card-text">Interview Ready</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Landing
