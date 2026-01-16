import { useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import './Landing.css'

function Landing() {
  const navigate = useNavigate()
  const [isLoaded, setIsLoaded] = useState(false)
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 })
  const fullTitle = 'frymyresume.cv'
  const [typedTitle, setTypedTitle] = useState('')
  const [isTitleTyped, setIsTitleTyped] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsLoaded(true)
    }, 100)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    if (!isLoaded) return

    const reduceMotion =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches

    if (reduceMotion) {
      setTypedTitle(fullTitle)
      setIsTitleTyped(true)
      return
    }

    setTypedTitle('')
    setIsTitleTyped(false)

    let index = 0
    let isCancelled = false
    let startTimeoutId: number | undefined
    let nextTimeoutId: number | undefined

    const scheduleNext = () => {
      if (isCancelled) return

      index += 1
      setTypedTitle(fullTitle.slice(0, index))

      if (index >= fullTitle.length) {
        setIsTitleTyped(true)
        return
      }

      const nextChar = fullTitle[index] ?? ''
      const base = 55
      const jitter = Math.floor(Math.random() * 35)
      const punctuationPause = nextChar === '.' ? 160 : 0
      const delay = base + jitter + punctuationPause

      nextTimeoutId = window.setTimeout(scheduleNext, delay)
    }

    startTimeoutId = window.setTimeout(() => {
      scheduleNext()
    }, 80)

    return () => {
      isCancelled = true
      if (startTimeoutId) window.clearTimeout(startTimeoutId)
      if (nextTimeoutId) window.clearTimeout(nextTimeoutId)
    }
  }, [isLoaded])

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMousePosition({
        x: (e.clientX / window.innerWidth - 0.5) * 20,
        y: (e.clientY / window.innerHeight - 0.5) * 20,
      })
    }

    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [])

  return (
    <div className="landing" style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <div className="landing-split">
        {/* Left Side - Content */}
        <div className={`landing-left ${isLoaded ? 'loaded' : ''}`}>
          <div className="landing-content">
            <div className="brand-section">
              <h1 className={`brand-title ${isTitleTyped ? 'typing-done' : 'typing'}`} aria-label={fullTitle}>
                {typedTitle}
                <span className="title-cursor">|</span>
              </h1>
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
            <div
              className="demo-video"
              style={{
                transform: `perspective(1000px) rotateY(${mousePosition.x * 0.02}deg) rotateX(${-mousePosition.y * 0.02}deg)`,
                transition: 'transform 0.1s ease-out',
              }}
            >
              <video
                className="demo-video-element"
                autoPlay
                loop
                muted
                playsInline
                preload="auto"
              >
                <source src="/demo.mp4" type="video/mp4" />
                Your browser does not support the video tag.
              </video>
            </div>

            <div
              className="floating-cards-wrap"
              style={{
                transform: `translate(${mousePosition.x * 0.5}px, ${mousePosition.y * 0.5}px)`,
                transition: 'transform 0.1s ease-out',
              }}
            >
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
    </div>
  )
}

export default Landing
