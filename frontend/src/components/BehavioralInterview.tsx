import { useState, useEffect, useRef } from 'react'
import './BehavioralInterview.css'

interface BehavioralInterviewProps {
  company: string
  role: string
  onComplete: (score: number) => void
}

function BehavioralInterview({ company, role, onComplete }: BehavioralInterviewProps) {
  const [isRecording, setIsRecording] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentQuestion, setCurrentQuestion] = useState<string>('')
  const [questionIndex, setQuestionIndex] = useState(0)
  const [sessionId, setSessionId] = useState<string>('')
  const [error, setError] = useState<string>('')
  const [totalQuestions, setTotalQuestions] = useState(3)
  const audioRef = useRef<HTMLAudioElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const currentQuestionRef = useRef<string>('')

  useEffect(() => {
    startInterview()
    return () => {
      if (mediaRecorderRef.current && isRecording) {
        mediaRecorderRef.current.stop()
      }
    }
  }, [])

  const startInterview = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/start-voice-interview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company, role })
      })
      const data = await response.json()
      console.log('Start interview response:', data)

      setSessionId(data.session_id)
      setTotalQuestions(data.total_questions || 3)

      // Set question index from backend response (defaults to 0 if not provided)
      const questionNum = data.question_number !== undefined ? data.question_number - 1 : 0
      setQuestionIndex(questionNum)

      // Set question text
      const questionText = data.first_question || ''
      if (questionText) {
        setCurrentQuestion(questionText)
      }

      // Play audio after all state is set, or just continue if no audio
      if (data.audio_base64 && questionText) {
        playAudioFromBase64(data.audio_base64, questionText)
      } else if (questionText && !data.audio_base64) {
        console.log('No audio available, displaying text only')
        setIsPlaying(false)
      }
    } catch (err) {
      setError('Failed to start interview')
      console.error(err)
    }
  }

  const playAudioFromBase64 = (base64Audio: string, questionText: string) => {
    if (audioRef.current) {
      console.log('Playing audio for question:', questionText.substring(0, 50))

      // Stop any currently playing audio
      if (!audioRef.current.paused) {
        audioRef.current.pause()
      }
      audioRef.current.currentTime = 0

      setIsPlaying(true)

      // Store the question text that corresponds to this audio
      currentQuestionRef.current = questionText

      const binaryString = atob(base64Audio)
      const bytes = new Uint8Array(binaryString.length)
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i)
      }
      const blob = new Blob([bytes], { type: 'audio/mpeg' })
      const audioUrl = URL.createObjectURL(blob)
      audioRef.current.src = audioUrl

      // Wait for audio to be ready before playing
      audioRef.current.onloadeddata = () => {
        console.log('Audio loaded, starting playback')
        audioRef.current?.play().catch(err => {
          console.error('Audio play failed:', err)
          setIsPlaying(false)
        })
      }

      audioRef.current.onended = () => {
        console.log('Audio playback ended')
        setIsPlaying(false)
        URL.revokeObjectURL(audioUrl)
      }

      audioRef.current.onerror = (e) => {
        console.error('Audio playback error:', e)
        setIsPlaying(false)
        URL.revokeObjectURL(audioUrl)
      }
    }
  }

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' })
        await sendResponse(audioBlob)
        stream.getTracks().forEach(track => track.stop())
      }

      mediaRecorder.start()
      setIsRecording(true)
    } catch (err) {
      setError('Failed to access microphone')
      console.error(err)
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
    }
  }

  const sendResponse = async (audioBlob: Blob) => {
    try {
      const formData = new FormData()
      formData.append('audio', audioBlob, 'response.wav')
      formData.append('session_id', sessionId)

      const response = await fetch('http://localhost:8000/api/voice-response', {
        method: 'POST',
        body: formData
      })

      const data = await response.json()
      console.log('Backend response:', data)

      if (data.completed) {
        // Interview complete
        console.log('Interview completed with score:', data.score)
        // Ensure score is a valid number
        const finalScore = typeof data.score === 'number' ? data.score : 0
        onComplete(finalScore)
      } else {
        // Next question/response
        console.log('Moving to question', data.question_number, 'with text:', data.next_question?.substring(0, 50))

        // Wait for any playing audio to finish before updating
        if (isPlaying && audioRef.current) {
          audioRef.current.pause()
          setIsPlaying(false)
        }

        // Update question index first (ensure question_number exists and is valid)
        if (data.question_number !== undefined && data.question_number !== null) {
          setQuestionIndex(data.question_number - 1)
        }

        // Update question text only if we have a valid next_question
        const nextQuestionText = data.next_question || ''
        if (nextQuestionText) {
          setCurrentQuestion(nextQuestionText)
        }

        // Play audio last, after state is updated, or just continue if no audio
        if (data.audio_base64 && nextQuestionText) {
          playAudioFromBase64(data.audio_base64, nextQuestionText)
        } else if (nextQuestionText && !data.audio_base64) {
          console.log('No audio available, displaying text only')
          setIsPlaying(false)
        }
      }
    } catch (err) {
      setError('Failed to send response')
      console.error(err)
    }
  }

  return (
    <div className="behavioral-interview">
      <div className="interview-status">
        <div className="question-number">Question {questionIndex + 1} of {totalQuestions}</div>
        <div className="recording-indicator">
          {isRecording && <span className="recording-dot"></span>}
          {isRecording ? 'Recording...' : isPlaying ? 'Listening...' : 'Ready'}
        </div>
      </div>

      <div className="question-display">
        <h2>Interviewer</h2>
        <p className="question-text">{currentQuestion || 'Starting interview...'}</p>
      </div>

      <div className="response-section">
        <h3>Your Response</h3>
        
        <div className="controls">
          {!isPlaying && !isRecording && (
            <button
              onClick={startRecording}
              className="record-button"
            >
              Start Recording
            </button>
          )}
          
          {isRecording && (
            <button
              onClick={stopRecording}
              className="stop-button"
            >
              Stop Recording
            </button>
          )}

          {isPlaying && (
            <div className="playing-indicator">Please wait for the question to finish...</div>
          )}
        </div>
      </div>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      <audio ref={audioRef} />
    </div>
  )
}

export default BehavioralInterview
