import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import Landing from './pages/Landing'
import ResumeReview from './pages/ResumeReview'
import JobSimulator from './pages/JobSimulator'
import Login from './pages/Login'
import Register from './pages/Register'
import Profile from './pages/Profile'
import OAuthCallback from './pages/OAuthCallback'
import ProtectedRoute from './components/ProtectedRoute'

function App() {
  console.log('App component rendering')

  return (
    <AuthProvider>
      <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
        <Router>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/auth/callback" element={<OAuthCallback />} />
            <Route path="/resume-review" element={<ResumeReview />} />
            <Route path="/job-simulator" element={<JobSimulator />} />
            <Route
              path="/profile"
              element={
                <ProtectedRoute>
                  <Profile />
                </ProtectedRoute>
              }
            />
          </Routes>
        </Router>
      </div>
    </AuthProvider>
  )
}

export default App
