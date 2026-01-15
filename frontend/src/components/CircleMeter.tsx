import { useId, useState, useEffect } from 'react'
import './CircleMeter.css'

interface CircleMeterProps {
  score: number
  size?: number
}

function CircleMeter({ score, size = 240 }: CircleMeterProps) {
  const gradientId = useId()
  const [animatedScore, setAnimatedScore] = useState(0)
  const radius = (size - 32) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (animatedScore / 100) * circumference

  useEffect(() => {
    // Animate from 0 to score over 1.5 seconds
    const duration = 1500
    const steps = 60
    const increment = score / steps
    const stepTime = duration / steps

    let currentStep = 0
    const timer = setInterval(() => {
      currentStep++
      if (currentStep >= steps) {
        setAnimatedScore(score)
        clearInterval(timer)
      } else {
        setAnimatedScore(Math.min(increment * currentStep, score))
      }
    }, stepTime)

    return () => clearInterval(timer)
  }, [score])

  const getAccentOpacity = (value: number) => {
    // Keep the wheel on-theme (red), but subtly reflect strength.
    if (value >= 85) return 1
    if (value >= 70) return 0.92
    if (value >= 55) return 0.84
    if (value >= 40) return 0.76
    return 0.68
  }

  const getLabel = (score: number) => {
    if (score >= 85) return 'FAANG Ready'
    if (score >= 75) return 'Strong Candidate'
    if (score >= 65) return 'Competitive'
    if (score >= 60) return 'Decent'
    if (score >= 45) return 'Needs Work'
    return 'Major Gaps'
  }

  return (
    <div className="circle-meter-container">
      <svg width={size} height={size} className="circle-meter-svg">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--accent-light, #ff6b6b)" stopOpacity={getAccentOpacity(score)} />
            <stop offset="55%" stopColor="var(--accent, #ef4444)" stopOpacity={getAccentOpacity(score)} />
            <stop offset="100%" stopColor="var(--accent-hover, #dc2626)" stopOpacity={getAccentOpacity(score)} />
          </linearGradient>
        </defs>
        <circle
          className="circle-meter-background"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth="20"
        />
        <circle
          className="circle-meter-progress"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth="20"
          stroke={`url(#${gradientId})`}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="circle-meter-content">
        <div className="circle-meter-score">{Math.round(animatedScore)}</div>
        <div className="circle-meter-label">{getLabel(score)}</div>
      </div>
    </div>
  )
}

export default CircleMeter
