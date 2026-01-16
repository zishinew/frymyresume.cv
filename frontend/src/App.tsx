import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import ResumeReview from './pages/ResumeReview'
import JobSimulator from './pages/JobSimulator'

function App() {
  console.log('App component rendering')

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <Router>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/resume-review" element={<ResumeReview />} />
          <Route path="/job-simulator" element={<JobSimulator />} />
        </Routes>
      </Router>
    </div>
  )
}

export default App
