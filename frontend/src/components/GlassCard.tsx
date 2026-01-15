import type { ReactNode, CSSProperties } from 'react'
import './GlassCard.css'

interface GlassCardProps {
  children: ReactNode
  variant?: 'default' | 'strong' | 'solid'
  hover?: boolean
  glow?: boolean
  glowColor?: 'accent' | 'success' | 'none'
  className?: string
  style?: CSSProperties
  onClick?: () => void
}

export default function GlassCard({
  children,
  variant = 'default',
  hover = false,
  glow = false,
  glowColor = 'none',
  className = '',
  style,
  onClick
}: GlassCardProps) {
  const variantClass = variant === 'strong' ? 'glass-card-strong' : variant === 'solid' ? 'glass-card-solid' : 'glass-card'
  const hoverClass = hover ? 'glass-card-hover' : ''
  const glowClass = glow ? `glass-card-glow glass-card-glow-${glowColor}` : ''

  return (
    <div
      className={`glass-card-base ${variantClass} ${hoverClass} ${glowClass} ${className}`.trim()}
      style={style}
      onClick={onClick}
    >
      {children}
    </div>
  )
}
