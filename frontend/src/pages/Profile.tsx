import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../services/api'
import { API_BASE_URL } from '../config'
import { supabase } from '../lib/supabase'
import './Profile.css'

interface JobApplication {
  id: number
  job_source: string
  company: string
  role: string
  difficulty: string
  location: string | null
  screening_passed: boolean | null
  technical_passed: boolean | null
  technical_score: number | null
  behavioral_passed: boolean | null
  behavioral_score: number | null
  final_hired: boolean | null
  final_weighted_score: number | null
  completed: boolean
  current_stage: string
  started_at: string
  completed_at: string | null
}

interface JobStats {
  total_simulations: number
  completed_simulations: number
  successful_simulations: number
  success_rate: number
  by_difficulty: Record<string, { total: number; passed: number }>
}

interface FriendUser {
  id: number
  username: string
  profile_picture: string | null
}

interface FriendRequest {
  id: number
  requester_id: number
  recipient_id: number
  status: string
  created_at: string
  requester: FriendUser
}

interface NotificationItem {
  id: number
  type: string
  message: string
  data: string | null
  is_read: boolean
  created_at: string
}

export default function Profile() {
  const navigate = useNavigate()
  const { user, logout, refreshUser } = useAuth()
  const [jobs, setJobs] = useState<JobApplication[]>([])
  const [stats, setStats] = useState<JobStats | null>(null)
  const [filter, setFilter] = useState<string>('all')
  const [isLoading, setIsLoading] = useState(true)
  const [expandedJob, setExpandedJob] = useState<number | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [profilePicture, setProfilePicture] = useState('')
  const [profileFile, setProfileFile] = useState<File | null>(null)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [accountStatus, setAccountStatus] = useState<string | null>(null)
  const [passwordStatus, setPasswordStatus] = useState<string | null>(null)
  const [uploadStatus, setUploadStatus] = useState<string | null>(null)
  const [friendQuery, setFriendQuery] = useState('')
  const [friendResults, setFriendResults] = useState<FriendUser[]>([])
  const [friendRequests, setFriendRequests] = useState<FriendRequest[]>([])
  const [friends, setFriends] = useState<FriendUser[]>([])
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [friendStatus, setFriendStatus] = useState<string | null>(null)
  const [isEntering, setIsEntering] = useState(false)

  useEffect(() => {
    fetchData()
  }, [filter])

  useEffect(() => {
    loadFriendsData()
  }, [])

  useEffect(() => {
    if (!user) return
    setUsername(user.username || '')
    setEmail(user.email || '')
    setProfilePicture(user.profile_picture || '')
  }, [user])

  useEffect(() => {
    const timer = window.setTimeout(() => setIsEntering(true), 50)
    return () => window.clearTimeout(timer)
  }, [])

  const fetchData = async () => {
    setIsLoading(true)
    try {
      const [jobsRes, statsRes] = await Promise.all([
        api.get(`/api/jobs/history${filter !== 'all' ? `?status_filter=${filter}` : ''}`),
        api.get('/api/jobs/stats'),
      ])

      if (jobsRes.ok) {
        setJobs(await jobsRes.json())
      }
      if (statsRes.ok) {
        setStats(await statsRes.json())
      }
    } catch (error) {
      console.error('Failed to fetch data:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const loadFriendsData = async () => {
    try {
      const [friendsRes, requestsRes, notificationsRes] = await Promise.all([
        api.get('/api/friends/list'),
        api.get('/api/friends/requests'),
        api.get('/api/friends/notifications'),
      ])

      if (friendsRes.ok) {
        setFriends(await friendsRes.json())
      }
      if (requestsRes.ok) {
        setFriendRequests(await requestsRes.json())
      }
      if (notificationsRes.ok) {
        const data = await notificationsRes.json()
        setNotifications(data.items || [])
        setUnreadCount(data.unread_count || 0)
      }
    } catch (error) {
      console.error('Failed to load friends data:', error)
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  const handleAccountSave = async () => {
    setAccountStatus(null)
    const response = await api.put('/api/users/account', {
      username,
      email,
      profile_picture: profilePicture,
    })

    if (!response.ok) {
      const error = await response.json()
      setAccountStatus(error.detail || 'Failed to update account')
      return
    }

    setAccountStatus('Account updated')
    await refreshUser()
  }

  const handleProfileUpload = async () => {
    setUploadStatus(null)
    if (!profileFile) {
      setUploadStatus('Select an image to upload')
      return
    }

    const formData = new FormData()
    formData.append('file', profileFile)

    // Get token from Supabase session
    const { data: { session } } = await supabase.auth.getSession()
    const token = session?.access_token
    const response = await fetch(`${API_BASE_URL}/api/users/profile-picture`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json()
      setUploadStatus(error.detail || 'Failed to upload image')
      return
    }

    const data = await response.json()
    setProfilePicture(data.profile_picture || '')
    setProfileFile(null)
    setUploadStatus('Profile picture updated')
    await refreshUser()
  }

  const handleFriendSearch = async () => {
    if (!friendQuery.trim()) return
    const response = await api.get(`/api/friends/search?q=${encodeURIComponent(friendQuery.trim())}`)
    if (!response.ok) return
    setFriendResults(await response.json())
  }

  const handleSendRequest = async (username: string) => {
    setFriendStatus(null)
    const response = await api.post('/api/friends/request', { username })
    if (!response.ok) {
      const error = await response.json()
      setFriendStatus(error.detail || 'Could not send request')
      return
    }
    setFriendStatus('Friend request sent')
    setFriendResults([])
    setFriendQuery('')
  }

  const handleAcceptRequest = async (requestId: number) => {
    await api.post(`/api/friends/requests/${requestId}/accept`)
    loadFriendsData()
  }

  const handleDeclineRequest = async (requestId: number) => {
    await api.post(`/api/friends/requests/${requestId}/decline`)
    loadFriendsData()
  }

  const markNotificationRead = async (notificationId: number) => {
    await api.post(`/api/friends/notifications/${notificationId}/read`)
    loadFriendsData()
  }

  const handlePasswordSave = async () => {
    setPasswordStatus(null)

    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordStatus('Fill out all password fields')
      return
    }

    if (newPassword !== confirmPassword) {
      setPasswordStatus('Passwords do not match')
      return
    }

    const response = await api.put('/api/users/password', {
      current_password: currentPassword,
      new_password: newPassword,
    })

    if (!response.ok) {
      const error = await response.json()
      setPasswordStatus(error.detail || 'Failed to update password')
      return
    }

    setPasswordStatus('Password updated')
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
  }

  const getStatusBadge = (job: JobApplication) => {
    if (job.final_hired) {
      return <span className="status-badge success">Hired</span>
    }
    if (job.completed && !job.final_hired) {
      return <span className="status-badge rejected">Not Hired</span>
    }
    return <span className="status-badge in-progress">In Progress</span>
  }

  const getDifficultyBadge = (difficulty: string) => {
    const colors: Record<string, string> = {
      easy: 'easy',
      medium: 'medium',
      hard: 'hard',
    }
    return <span className={`difficulty-badge ${colors[difficulty] || ''}`}>{difficulty}</span>
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  }

  return (
    <div className={`profile-page ${isEntering ? 'entered' : ''}`}>
      <header className="profile-header">
        <Link to="/" className="profile-logo">
          <img src="/icon.png" alt="frymyresume.cv" />
        </Link>
        <div className="profile-actions">
          <button
            onClick={() => setSettingsOpen((prev) => !prev)}
            className="settings-toggle cta-secondary"
            aria-label="Account settings"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z" />
              <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.54V22a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.54 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.54-1H3a2 2 0 1 1 0-4h.06a1.7 1.7 0 0 0 1.54-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 8.9 4.6a1.7 1.7 0 0 0 1-1.54V3a2 2 0 1 1 4 0v.06a1.7 1.7 0 0 0 1 1.54 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.07.23.1.47.1.72s-.03.49-.1.72a1.7 1.7 0 0 0 1.54 1H21a2 2 0 1 1 0 4h-.06a1.7 1.7 0 0 0-1.54 1z" />
            </svg>
            {unreadCount > 0 && <span className="notification-badge">{unreadCount}</span>}
          </button>
          <button onClick={handleLogout} className="logout-btn cta-secondary">
            Sign out
          </button>
        </div>
      </header>

      <main className="profile-main">
        <div className="profile-content">
          {/* User Info Section */}
          <section className="user-section">
            <div className="user-card card-animate">
              <div className="user-avatar">
                {user?.profile_picture ? (
                  <img src={user.profile_picture} alt={user.username || 'Profile'} />
                ) : (
                  <div className="avatar-placeholder">
                    {(user?.username || user?.email || '?')[0].toUpperCase()}
                  </div>
                )}
              </div>
              <div className="user-info">
                <h1>{user?.username || 'Anonymous User'}</h1>
                <p className="user-email">{user?.email}</p>
                <p className="user-provider">
                  Signed in with {user?.auth_provider === 'local' ? 'email' : user?.auth_provider}
                </p>
              </div>
            </div>
          </section>

          <section className={`settings-section card-animate ${settingsOpen ? 'open' : ''}`}>
            <header className="settings-header">
              <div>
                <h2>Account Settings</h2>
                <p>Update your profile details and password</p>
              </div>
              <button
                className="settings-toggle-btn cta-secondary"
                onClick={() => setSettingsOpen((prev) => !prev)}
              >
                {settingsOpen ? 'Hide' : 'Edit'}
              </button>
            </header>

            <div className="settings-grid">
              <div className="settings-card">
                <h3>Profile</h3>
                <label>
                  Username
                  <input value={username} onChange={(e) => setUsername(e.target.value)} />
                </label>
                <label>
                  Email
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                </label>
                <label>
                  Profile picture
                  <span className="file-upload">
                    <input
                      type="file"
                      accept="image/*"
                      onChange={(e) => setProfileFile(e.target.files?.[0] || null)}
                    />
                    <span className="file-upload-button">Choose image</span>
                    <span className="file-upload-name">
                      {profileFile?.name || 'No file selected'}
                    </span>
                  </span>
                </label>
                <div className="settings-actions">
                  <button className="settings-save cta-primary" onClick={handleProfileUpload}>Upload image</button>
                  <button className="settings-save cta-secondary" onClick={handleAccountSave}>Save changes</button>
                </div>
                {uploadStatus && <div className="settings-status">{uploadStatus}</div>}
                {accountStatus && <div className="settings-status">{accountStatus}</div>}
              </div>

              <div className="settings-card">
                <h3>Password</h3>
                <label>
                  Current password
                  <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
                </label>
                <label>
                  New password
                  <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
                </label>
                <label>
                  Confirm new password
                  <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
                </label>
                {passwordStatus && <div className="settings-status">{passwordStatus}</div>}
                <button className="settings-save cta-primary" onClick={handlePasswordSave}>Update password</button>
              </div>
            </div>
          </section>

          <section className="friends-section card-animate">
            <header className="friends-header">
              <div>
                <h2>Friends</h2>
                <p>Search users and manage friend requests</p>
              </div>
            </header>

            <div className="friends-search">
              <input
                value={friendQuery}
                onChange={(e) => setFriendQuery(e.target.value)}
                placeholder="Search by username"
              />
              <button className="cta-primary" onClick={handleFriendSearch}>Search</button>
            </div>
            {friendStatus && <div className="settings-status">{friendStatus}</div>}

            {friendResults.length > 0 && (
              <div className="friends-results">
                {friendResults.map((result) => (
                  <div key={result.id} className="friends-row">
                    <div className="friends-user">
                      {result.profile_picture ? (
                        <img src={result.profile_picture} alt={result.username} />
                      ) : (
                        <span>{result.username[0].toUpperCase()}</span>
                      )}
                      <span>{result.username}</span>
                    </div>
                    <button className="cta-secondary" onClick={() => handleSendRequest(result.username)}>
                      Add friend
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="friends-columns">
              <div>
                <h3>Requests</h3>
                {friendRequests.length === 0 ? (
                  <p className="friends-empty">No pending requests</p>
                ) : (
                  friendRequests.map((request) => (
                    <div key={request.id} className="friends-row">
                      <div className="friends-user">
                        {request.requester.profile_picture ? (
                          <img src={request.requester.profile_picture} alt={request.requester.username} />
                        ) : (
                          <span>{request.requester.username[0].toUpperCase()}</span>
                        )}
                        <span>{request.requester.username}</span>
                      </div>
                      <div className="friends-actions">
                        <button className="cta-primary" onClick={() => handleAcceptRequest(request.id)}>Accept</button>
                        <button className="cta-secondary" onClick={() => handleDeclineRequest(request.id)}>Decline</button>
                      </div>
                    </div>
                  ))
                )}
              </div>
              <div>
                <h3>Friends list</h3>
                {friends.length === 0 ? (
                  <p className="friends-empty">No friends yet</p>
                ) : (
                  friends.map((friend) => (
                    <div key={friend.id} className="friends-row">
                      <div className="friends-user">
                        {friend.profile_picture ? (
                          <img src={friend.profile_picture} alt={friend.username} />
                        ) : (
                          <span>{friend.username[0].toUpperCase()}</span>
                        )}
                        <span>{friend.username}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>

          <section className="notifications-section card-animate">
            <header className="friends-header">
              <div>
                <h2>Notifications</h2>
                <p>Latest friend activity</p>
              </div>
            </header>

            {notifications.length === 0 ? (
              <p className="friends-empty">No notifications yet</p>
            ) : (
              <div className="notifications-list">
                {notifications.map((note) => (
                  <div key={note.id} className={`notification-row ${note.is_read ? 'read' : ''}`}>
                    <div>
                      <p>{note.message}</p>
                      <span>{new Date(note.created_at).toLocaleString()}</span>
                    </div>
                    {!note.is_read && (
                      <button className="cta-secondary" onClick={() => markNotificationRead(note.id)}>
                        Mark read
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Stats Section */}
          {stats && (
            <section className="stats-section card-animate">
              <h2>Your Statistics</h2>
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-value">{stats.total_simulations}</div>
                  <div className="stat-label">Total Simulations</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{stats.completed_simulations}</div>
                  <div className="stat-label">Completed</div>
                </div>
                <div className="stat-card highlight">
                  <div className="stat-value">{stats.successful_simulations}</div>
                  <div className="stat-label">Jobs Gotten Into</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{stats.success_rate}%</div>
                  <div className="stat-label">Success Rate</div>
                </div>
              </div>

              <div className="difficulty-stats">
                <h3>By Difficulty</h3>
                <div className="difficulty-grid">
                  {['easy', 'medium', 'hard'].map((diff) => (
                    <div key={diff} className={`difficulty-card ${diff}`}>
                      <div className="difficulty-name">{diff}</div>
                      <div className="difficulty-numbers">
                        <span className="passed">{stats.by_difficulty[diff]?.passed || 0}</span>
                        <span className="separator">/</span>
                        <span className="total">{stats.by_difficulty[diff]?.total || 0}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          )}

          {/* Job History Section */}
          <section className="jobs-section card-animate">
            <div className="jobs-header">
              <h2>Simulation History</h2>
              <div className="filter-tabs">
                {[
                  { value: 'all', label: 'All' },
                  { value: 'passed', label: 'Passed' },
                  { value: 'rejected', label: 'Rejected' },
                  { value: 'in_progress', label: 'In Progress' },
                ].map((tab) => (
                  <button
                    key={tab.value}
                    className={`filter-tab cta-secondary ${filter === tab.value ? 'active' : ''}`}
                    onClick={() => setFilter(tab.value)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {isLoading ? (
              <div className="loading-state">Loading...</div>
            ) : jobs.length === 0 ? (
              <div className="empty-state">
                <p>No simulations found</p>
                <Link to="/job-simulator" className="start-btn cta-primary">
                  Start a simulation
                </Link>
              </div>
            ) : (
              <div className="jobs-list">
                {jobs.map((job) => (
                  <div
                    key={job.id}
                    className={`job-card ${expandedJob === job.id ? 'expanded' : ''}`}
                    onClick={() => setExpandedJob(expandedJob === job.id ? null : job.id)}
                  >
                    <div className="job-summary">
                      <div className="job-main">
                        <h3>{job.role}</h3>
                        <p className="job-company">{job.company}</p>
                      </div>
                      <div className="job-badges">
                        {getDifficultyBadge(job.difficulty)}
                        {getStatusBadge(job)}
                      </div>
                      <div className="job-date">{formatDate(job.started_at)}</div>
                    </div>

                    {expandedJob === job.id && (
                      <div className="job-details">
                        <div className="stages-progress">
                          <div
                            className={`stage ${job.screening_passed === true ? 'passed' : job.screening_passed === false ? 'failed' : 'pending'}`}
                          >
                            <div className="stage-icon">
                              {job.screening_passed === true
                                ? '✓'
                                : job.screening_passed === false
                                  ? '✗'
                                  : '○'}
                            </div>
                            <div className="stage-name">Screening</div>
                          </div>
                          <div className="stage-connector" />
                          <div
                            className={`stage ${job.technical_passed === true ? 'passed' : job.technical_passed === false ? 'failed' : 'pending'}`}
                          >
                            <div className="stage-icon">
                              {job.technical_passed === true
                                ? '✓'
                                : job.technical_passed === false
                                  ? '✗'
                                  : '○'}
                            </div>
                            <div className="stage-name">Technical</div>
                            {job.technical_score !== null && (
                              <div className="stage-score">{job.technical_score.toFixed(0)}%</div>
                            )}
                          </div>
                          <div className="stage-connector" />
                          <div
                            className={`stage ${job.behavioral_passed === true ? 'passed' : job.behavioral_passed === false ? 'failed' : 'pending'}`}
                          >
                            <div className="stage-icon">
                              {job.behavioral_passed === true
                                ? '✓'
                                : job.behavioral_passed === false
                                  ? '✗'
                                  : '○'}
                            </div>
                            <div className="stage-name">Behavioral</div>
                            {job.behavioral_score !== null && (
                              <div className="stage-score">{job.behavioral_score.toFixed(0)}%</div>
                            )}
                          </div>
                        </div>

                        {job.final_weighted_score !== null && (
                          <div className="final-score">
                            <span>Final Score:</span>
                            <strong>{job.final_weighted_score.toFixed(1)}%</strong>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}
