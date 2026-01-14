import { useState, useEffect, useRef } from 'react'
import './BehavioralInterview.css'

interface BehavioralInterviewLiveV2Props {
  company: string
  role: string
  onComplete: (score: number) => void
}

function BehavioralInterviewLiveV2({ company, role, onComplete }: BehavioralInterviewLiveV2Props) {
  const [isConnected, setIsConnected] = useState(false)
  const [currentQuestion, setCurrentQuestion] = useState<string>('')
  const [questionIndex, setQuestionIndex] = useState(0)
  const [error, setError] = useState<string>('')
  const [totalQuestions] = useState(3)

  const wsRef = useRef<WebSocket | null>(null)
  const apiKeyRef = useRef<string>('')

  useEffect(() => {
    startInterview()
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  const startInterview = async () => {
    try {
      // Get API key from backend
      const response = await fetch('http://localhost:8000/api/get-gemini-token')
      const data = await response.json()
      apiKeyRef.current = data.api_key

      // Connect directly to Gemini Live API
      const ws = new WebSocket(
        `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key=${apiKeyRef.current}`
      )
      wsRef.current = ws

      ws.onopen = () => {
        console.log('Connected to Gemini Live API')
        setIsConnected(true)

        // Send setup message
        const setupMessage = {
          setup: {
            model: 'models/gemini-2.0-flash-exp',
            generation_config: {
              response_modalities: ['AUDIO']
            },
            system_instruction: {
              parts: [{
                text: `You are a professional behavioral interviewer at ${company} conducting an interview for a ${role} position.

Your role:
1. Ask exactly 3 behavioral interview questions, one at a time
2. Listen carefully to each response
3. After the candidate answers, acknowledge briefly (1-2 sentences) and ask the next question
4. Questions should be relevant to ${role} and assess: problem-solving, teamwork, conflict resolution, leadership, or past experiences
5. Keep questions concise and professional (1-2 sentences)
6. After 3 questions, thank the candidate and end

Start by asking the first question.`
              }]
            }
          }
        }

        ws.send(JSON.stringify(setupMessage))
        console.log('Setup message sent')
      }

      ws.onmessage = (event) => {
        const message = JSON.parse(event.data)
        console.log('Received from Gemini:', message)

        // Handle server content (Gemini's response)
        if (message.serverContent) {
          const parts = message.serverContent.modelTurn?.parts || []

          parts.forEach((part: any) => {
            // Text transcript
            if (part.text) {
              setCurrentQuestion(part.text)
              console.log('Question:', part.text)
            }

            // Audio data
            if (part.inlineData) {
              playAudio(part.inlineData.data)
            }
          })

          // Turn complete
          if (message.serverContent.turnComplete) {
            const newIndex = questionIndex + 1
            setQuestionIndex(newIndex)
            console.log(`Question ${newIndex + 1} complete`)

            if (newIndex >= totalQuestions) {
              // Interview complete
              setTimeout(() => {
                onComplete(75) // Default score for now
                ws.close()
              }, 2000)
            }
          }
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        setError('Connection error')
      }

      ws.onclose = () => {
        console.log('Disconnected from Gemini')
        setIsConnected(false)
      }

    } catch (err) {
      console.error('Failed to start interview:', err)
      setError('Failed to connect')
    }
  }

  const playAudio = async (base64Audio: string) => {
    try {
      const audioContext = new AudioContext({ sampleRate: 24000 })
      const binaryString = atob(base64Audio)
      const bytes = new Uint8Array(binaryString.length)

      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i)
      }

      const audioBuffer = await audioContext.decodeAudioData(bytes.buffer)
      const source = audioContext.createBufferSource()
      source.buffer = audioBuffer
      source.connect(audioContext.destination)
      source.start(0)
    } catch (err) {
      console.error('Audio playback error:', err)
    }
  }

  const startSpeaking = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1
        }
      })

      const audioContext = new AudioContext({ sampleRate: 16000 })
      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(4096, 1, 1)

      processor.onaudioprocess = (e) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

        const inputData = e.inputBuffer.getChannelData(0)
        const pcmData = new Int16Array(inputData.length)

        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]))
          pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
        }

        const base64Audio = btoa(String.fromCharCode(...new Uint8Array(pcmData.buffer)))

        const message = {
          realtimeInput: {
            mediaChunks: [{
              mimeType: 'audio/pcm',
              data: base64Audio
            }]
          }
        }

        wsRef.current.send(JSON.stringify(message))
      }

      source.connect(processor)
      processor.connect(audioContext.destination)

    } catch (err) {
      console.error('Microphone error:', err)
      setError('Failed to access microphone')
    }
  }

  return (
    <div className="behavioral-interview">
      <div className="interview-status">
        <div className="question-number">Question {questionIndex + 1} of {totalQuestions}</div>
        <div className="recording-indicator">
          {isConnected ? 'Connected' : 'Connecting...'}
        </div>
      </div>

      <div className="question-display">
        <h2>Interviewer</h2>
        <p className="question-text">
          {currentQuestion || 'Starting interview...'}
        </p>
      </div>

      <div className="response-section">
        <h3>Your Response</h3>

        <div className="controls">
          {isConnected && (
            <button
              onClick={startSpeaking}
              className="record-button"
            >
              Start Speaking
            </button>
          )}

          <div className="live-interview-info">
            <p style={{ fontSize: '0.9rem', color: '#666', marginTop: '1rem' }}>
              💡 Direct connection to Gemini Live API - speak naturally!
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}
    </div>
  )
}

export default BehavioralInterviewLiveV2
