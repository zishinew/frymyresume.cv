import { useState, useEffect } from 'react'
import './CircleMeter.css'

interface CircleMeterProps {
  score: number
  size?: number
}

function CircleMeter({ score, size = 200 }: CircleMeterProps) {
  const [animatedScore, setAnimatedScore] = useState(0)
  const radius = (size - 20) / 2
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

  const getColor = (score: number) => {
    if (score >= 80) return '#22c55e' // green
    if (score >= 60) return '#3b82f6' // blue
    if (score >= 50) return '#f59e0b' // amber
    if (score >= 40) return '#f97316' // orange
    return '#ef4444' // red
  }

  const getLabel = (score: number) => {
    if (score >= 80) return 'Big Tech Ready'
    if (score >= 60) return 'Intermediate Level'
    if (score >= 50) return 'Startup Level'
    if (score >= 40) return 'Needs Improvement'
    return 'Significant Work Needed'
  }

  return (
    <div className="circle-meter-container">
      <svg width={size} height={size} className="circle-meter-svg">
        <circle
          className="circle-meter-background"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth="12"
        />
        <circle
          className="circle-meter-progress"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth="12"
          stroke={getColor(animatedScore)}
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
