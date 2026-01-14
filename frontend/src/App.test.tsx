// Temporary test file to verify React is working
// This will be a simple component that should definitely render

function TestApp() {
  return (
    <div style={{ 
      padding: '2rem', 
      color: 'white', 
      background: '#0a0a0a',
      minHeight: '100vh',
      fontSize: '24px'
    }}>
      <h1>React is Working!</h1>
      <p>If you see this, React is rendering correctly.</p>
      <p>Now let's check why the main app isn't showing...</p>
    </div>
  )
}

export default TestApp
