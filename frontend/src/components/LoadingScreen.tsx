import './LoadingScreen.css'

function LoadingScreen({ text }: { text?: string }) {
  return (
    <div className="loading-screen">
      <div className="loading-content">
        <div className="loading-dots">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <p className="loading-text">{text || 'Your resume is being read by recruiters...'}</p>
      </div>
    </div>
  )
}

export default LoadingScreen
