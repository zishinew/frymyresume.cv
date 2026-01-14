// Ultra-simple test to verify React is working
function SimpleApp() {
  return (
    <div style={{
      padding: '2rem',
      color: 'white',
      background: '#0a0a0a',
      minHeight: '100vh',
      fontSize: '20px',
      fontFamily: 'Arial, sans-serif'
    }}>
      <h1 style={{ color: '#6366f1' }}>React is Working!</h1>
      <p>If you see this, React is rendering correctly.</p>
      <p>The issue is likely in one of the components or routing.</p>
    </div>
  )
}

export default SimpleApp
