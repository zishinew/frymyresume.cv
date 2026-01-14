import { useState, useEffect, useRef } from 'react'
import './BehavioralInterview.css'
import LoadingScreen from './LoadingScreen'

interface BehavioralInterviewLiveProps {
  company: string
  role: string
  onComplete: (score: number, meta?: { disqualified?: boolean; flags?: any; scoring_version?: string }) => void
}

function BehavioralInterviewLive({ company, role, onComplete }: BehavioralInterviewLiveProps) {
  const [isConnected, setIsConnected] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [currentQuestion, setCurrentQuestion] = useState<string>('')
  const [questionIndex, setQuestionIndex] = useState(0)
  const [error, setError] = useState<string>('')
  const [totalQuestions] = useState(3)
  const [interviewStarted, setInterviewStarted] = useState(false)
  const [userTranscript, setUserTranscript] = useState<string>('')
  const [isReviewing, setIsReviewing] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const audioQueueRef = useRef<AudioBuffer[]>([])
  const isPlayingRef = useRef(false)
  const shouldCloseWsOnOpenRef = useRef(false)

  const isListeningRef = useRef(false)
  const interviewEndedRef = useRef(false)
  const hasSpokenThisTurnRef = useRef(false)
  const lastVoiceAtMsRef = useRef<number>(0)
  const endOfTurnSentRef = useRef(false)
  const preRollRef = useRef<string[]>([])
  const preRollMaxChunksRef = useRef(6)

  const mergeTranscript = (prev: string, next: string) => {
    const p = (prev || '').trim()
    const n = (next || '').trim()
    if (!n) return p
    if (!p) return n
    if (n === p) return p
    if (n.length >= p.length && (n.includes(p) || p.includes(n) || n.startsWith(p))) return n
    if (p.length > n.length && (p.includes(n) || p.startsWith(n))) return p
    return n.length >= p.length ? n : p
  }

  useEffect(() => {
    isListeningRef.current = isListening
  }, [isListening])

  useEffect(() => {
    connectWebSocket()

    return () => {
      cleanup()
    }
  }, [])

  const cleanup = () => {
    // Stop mic capture without sending an end-of-turn (we might be unmounting
    // due to interview completion or navigation).
    if (processorRef.current || mediaStreamRef.current) {
      stopListening(false, false)
    }

    // Stop audio stream
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop())
    }

    // Close audio processor
    if (processorRef.current) {
      processorRef.current.disconnect()
    }

    // Close audio context
    if (audioContextRef.current) {
      audioContextRef.current.close()
    }

    // Close WebSocket
    if (wsRef.current) {
      const ws = wsRef.current
      // If React StrictMode unmounts while CONNECTING, closing immediately
      // can log a scary warning. Close as soon as it opens instead.
      if (ws.readyState === WebSocket.CONNECTING) {
        shouldCloseWsOnOpenRef.current = true
      } else {
        ws.close()
      }
    }
  }

  const connectWebSocket = () => {
    try {
      const ws = new WebSocket('ws://localhost:8000/ws/behavioral-interview')
      wsRef.current = ws

      ws.onopen = () => {
        console.log('WebSocket connected')

        if (shouldCloseWsOnOpenRef.current) {
          shouldCloseWsOnOpenRef.current = false
          ws.close()
          return
        }

        setIsConnected(true)

        // Send initial data
        ws.send(JSON.stringify({
          company,
          role
        }))

        setInterviewStarted(true)
      }

      ws.onmessage = async (event) => {
        const message = JSON.parse(event.data)
        console.log('Received message:', message.type)

        switch (message.type) {
          case 'audio':
            // Received audio from Gemini
            await playAudioChunk(message.data, message.sample_rate)
            break

          case 'question':
            // Canonical interviewer question text (clean, non-transcribed)
            // Ensure we are not recording while the interviewer is speaking.
            if (isListeningRef.current) {
              stopListening(false, true)
            }
            if (typeof message.content === 'string') {
              setCurrentQuestion(message.content)
            }
            if (typeof message.question_number === 'number') {
              setQuestionIndex(message.question_number - 1)
            }
            break

          case 'text':
            // Received text transcript from Gemini
            if (message.speaker === 'interviewer') {
              // Do not overwrite the canonical question text (message.type === 'question').
              // The Live output transcription is often garbled; keep it separate if desired.
              // Ignore.
            } else if (message.speaker === 'candidate') {
              setUserTranscript((prev) => mergeTranscript(prev, message.content))
            }
            break

          case 'turn_complete':
            // Gemini finished asking a question
            setQuestionIndex(message.question_number - 1)
            console.log(`Question ${message.question_number} of ${message.total_questions}`)

            // Auto-start recording for the candidate's answer once the interviewer is done.
            // Wait for any queued TTS audio to finish playing so we don't capture it.
            if (!interviewEndedRef.current) {
              const waitForPlaybackToFinish = async () => {
                const startedAt = Date.now()
                while ((isPlayingRef.current || audioQueueRef.current.length > 0) && (Date.now() - startedAt) < 8000) {
                  await new Promise(resolve => setTimeout(resolve, 50))
                }
              }

              await waitForPlaybackToFinish()

              if (!isListeningRef.current) {
                await startListening()
              }
            }
            break

          case 'resume_listening':
            // Backend didn't get enough real audio to count as an answer.
            // Restart mic capture so the user can respond without clicking.
            if (!interviewEndedRef.current) {
              setUserTranscript('')
              if (!isListeningRef.current) {
                await startListening()
              }
            }
            break

          case 'reviewing':
            // Backend has started final evaluation.
            setIsReviewing(true)
            if (isListeningRef.current) {
              stopListening(false, true)
            }
            break

          case 'interview_complete':
            // Interview finished
            console.log('Interview complete with score:', message.score)
            setIsReviewing(false)
            interviewEndedRef.current = true
            onComplete(message.score, {
              disqualified: message.disqualified,
              flags: message.flags,
              scoring_version: message.scoring_version
            })
            cleanup()
            break

          case 'error':
            setError(message.message)
            setIsReviewing(false)
            console.error('Error from server:', message.message)
            break
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        setError('Connection error occurred')
        setIsConnected(false)
      }

      ws.onclose = () => {
        console.log('WebSocket closed')
        setIsConnected(false)
      }
    } catch (err) {
      console.error('Failed to connect:', err)
      setError('Failed to connect to server')
    }
  }

  const playAudioChunk = async (base64Audio: string, sampleRate?: number) => {
    try {
      // Initialize AudioContext if needed
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 24000 })
      }

      const audioContext = audioContextRef.current
      // Some browsers start AudioContext suspended until a user gesture.
      if (audioContext.state === 'suspended') {
        await audioContext.resume()
      }

      const pcmBytes = base64ToUint8Array(base64Audio)
      const rate = typeof sampleRate === 'number' ? sampleRate : 24000
      const audioBuffer = pcm16leToAudioBuffer(audioContext, pcmBytes, rate)

      // Add to queue and play
      audioQueueRef.current.push(audioBuffer)
      if (!isPlayingRef.current) {
        playNextAudioChunk()
      }
    } catch (err) {
      console.error('Error playing audio:', err)
    }
  }

  const base64ToUint8Array = (base64: string) => {
    const binaryString = atob(base64)
    const bytes = new Uint8Array(binaryString.length)
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i)
    }
    return bytes
  }

  const pcm16leToAudioBuffer = (audioContext: AudioContext, bytes: Uint8Array, sampleRate: number) => {
    // Expect 16-bit signed little-endian PCM
    const byteLength = bytes.byteLength - (bytes.byteLength % 2)
    const samples = byteLength / 2

    const audioBuffer = audioContext.createBuffer(1, samples, sampleRate)
    const channelData = audioBuffer.getChannelData(0)

    for (let i = 0, offset = 0; i < samples; i++, offset += 2) {
      const lo = bytes[offset]
      const hi = bytes[offset + 1]
      let sample = (hi << 8) | lo
      if (sample >= 0x8000) sample -= 0x10000
      channelData[i] = sample / 0x8000
    }

    return audioBuffer
  }

  const playNextAudioChunk = () => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false
      return
    }

    isPlayingRef.current = true
    const audioBuffer = audioQueueRef.current.shift()!
    const audioContext = audioContextRef.current!

    const source = audioContext.createBufferSource()
    source.buffer = audioBuffer
    source.connect(audioContext.destination)

    source.onended = () => {
      playNextAudioChunk()
    }

    source.start(0)
  }

  const startListening = async () => {
    try {
      if (interviewEndedRef.current) return
      if (isListeningRef.current) return

      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        }
      })

      mediaStreamRef.current = stream

      // Initialize AudioContext if needed
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 })
      }

      const audioContext = audioContextRef.current
      const source = audioContext.createMediaStreamSource(stream)

      // Create audio processor for streaming
      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      processorRef.current = processor

      // Voice activity detection (simple RMS threshold + silence timeout).
      // Ends the candidate turn when they've spoken and then paused.
      hasSpokenThisTurnRef.current = false
      lastVoiceAtMsRef.current = Date.now()
      endOfTurnSentRef.current = false

      const silenceMsToEndTurn = 2600
      const minSpeechMs = 450
      const minTurnMs = 1400
      const noiseCalibrateMs = 500
      const speechHoldMs = 250

      const turnStartMs = Date.now()
      let noiseRmsSum = 0
      let noiseRmsCount = 0
      let speechFrames = 0
      let speechMsAccum = 0
      let lastProcessMs = turnStartMs
      let lastSpeechEndMs = turnStartMs
      let noiseFloorRms = 0.0
      let emaRms = 0.0

      // Reset pre-roll buffer for this turn.
      preRollRef.current = []

      processor.onaudioprocess = (e) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
          return
        }

        const wasSpeech = hasSpokenThisTurnRef.current

        const inputData = e.inputBuffer.getChannelData(0)

        // Compute RMS for a basic VAD.
        let sumSquares = 0
        for (let i = 0; i < inputData.length; i++) {
          const v = inputData[i]
          sumSquares += v * v
        }
        const rms = Math.sqrt(sumSquares / inputData.length)

        const nowMs = Date.now()
        const dtMs = Math.max(0, nowMs - lastProcessMs)
        lastProcessMs = nowMs

        // Smooth RMS (EMA) to reduce spiky noise triggering speech.
        emaRms = emaRms * 0.8 + rms * 0.2

        // Calibrate background noise floor for the first short window.
        if (!hasSpokenThisTurnRef.current && (nowMs - turnStartMs) <= noiseCalibrateMs) {
          noiseRmsSum += emaRms
          noiseRmsCount += 1
          noiseFloorRms = noiseRmsCount > 0 ? (noiseRmsSum / noiseRmsCount) : 0.0
        }

        // Dynamic threshold: a multiple of noise floor, clamped to a sane minimum.
        const dynamicThreshold = Math.max(0.025, noiseFloorRms * 4.0)
        const isSpeechFrame = emaRms >= dynamicThreshold

        if (!hasSpokenThisTurnRef.current) {
          if (isSpeechFrame) {
            speechFrames += 1
            speechMsAccum += dtMs
            if (speechMsAccum >= minSpeechMs) {
              hasSpokenThisTurnRef.current = true
              lastVoiceAtMsRef.current = nowMs
            }
          } else {
            // Reset if we didn't get sustained speech.
            speechFrames = 0
            speechMsAccum = 0
          }
        } else {
          if (isSpeechFrame) {
            lastVoiceAtMsRef.current = nowMs
            lastSpeechEndMs = nowMs
          } else {
            // Treat speech as having ended; keep a short hold to avoid choppy stopping.
            if (nowMs - lastSpeechEndMs <= speechHoldMs) {
              lastVoiceAtMsRef.current = nowMs
            }
          }

          // End turn after sustained silence, but never too quickly.
          if (!endOfTurnSentRef.current) {
            const silenceMs = nowMs - lastVoiceAtMsRef.current
            const turnMs = nowMs - turnStartMs
            if (turnMs >= minTurnMs && silenceMs >= silenceMsToEndTurn) {
              endOfTurnSentRef.current = true
              // Defer stopping to avoid doing too much work inside onaudioprocess.
              setTimeout(() => stopListening(true, true), 0)
              return
            }
          }
        }

        // Convert Float32Array to Int16Array (PCM)
        const pcmData = new Int16Array(inputData.length)
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]))
          pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
        }

        // Always encode a small pre-roll so we don't miss the first word(s)
        // before VAD declares "speech".
        const base64Audio = btoa(String.fromCharCode(...new Uint8Array(pcmData.buffer)))

        if (!hasSpokenThisTurnRef.current) {
          preRollRef.current.push(base64Audio)
          if (preRollRef.current.length > preRollMaxChunksRef.current) {
            preRollRef.current.shift()
          }
        }

        const speechJustStarted = !wasSpeech && hasSpokenThisTurnRef.current

        // Once speech begins, flush pre-roll first.
        if (speechJustStarted) {
          const pre = preRollRef.current
          preRollRef.current = []
          for (const chunk of pre) {
            wsRef.current.send(JSON.stringify({ type: 'audio', data: chunk }))
          }
        }

        // Gate audio streaming until we've detected real speech.
        if (hasSpokenThisTurnRef.current) {
          wsRef.current.send(JSON.stringify({
            type: 'audio',
            data: base64Audio
          }))
        }
      }

      source.connect(processor)
      processor.connect(audioContext.destination)

      setIsListening(true)
      console.log('Started listening')
    } catch (err) {
      console.error('Failed to start listening:', err)
      setError('Failed to access microphone')
    }
  }

  const stopListening = (sendEndOfTurn: boolean = true, updateState: boolean = true) => {
    // Stop audio processing
    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current = null
    }

    // Stop media stream
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop())
      mediaStreamRef.current = null
    }

    // Notify backend that turn is complete
    if (sendEndOfTurn && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'end_of_turn',
        had_speech: hasSpokenThisTurnRef.current
      }))
    }

    if (updateState) {
      setIsListening(false)
    }
    console.log('Stopped listening')
  }

  return (
    <div className="behavioral-interview">
      {isReviewing && <LoadingScreen text="Your interview is being reviewed..." />}
      <div className="interview-status">
        <div className="question-number">Question {questionIndex + 1} of {totalQuestions}</div>
        <div className="recording-indicator">
          {!isConnected && <span>Connecting...</span>}
          {isConnected && !interviewStarted && <span>Starting interview...</span>}
          {isListening && <span className="recording-dot"></span>}
          {isConnected && (isReviewing ? 'Reviewing...' : (isListening ? 'Speaking...' : 'Waiting for your turn...'))}
        </div>
      </div>

      <div className="question-display">
        <h2>Interviewer</h2>
        <p className="question-text">
          {currentQuestion || 'Connecting to interviewer...'}
        </p>
      </div>

      <div className="response-section">
        <h3>Your Response</h3>

        {userTranscript && (
          <div style={{
            padding: '1rem',
            backgroundColor: '#f0f7ff',
            borderRadius: '8px',
            marginBottom: '1rem',
            border: '1px solid #d0e7ff'
          }}>
            <p style={{ fontSize: '0.85rem', color: '#666', marginBottom: '0.5rem' }}>
              What I heard:
            </p>
            <p style={{ fontSize: '0.95rem', color: '#333' }}>
              "{userTranscript}"
            </p>
          </div>
        )}

        <div className="controls">
          {!isConnected && (
            <div className="connecting-indicator">Connecting to interview...</div>
          )}
        </div>

        <div className="live-interview-info">
          <p style={{ fontSize: '0.9rem', color: '#666', marginTop: '1rem' }}>
            💡 This is a live AI interview using Google Gemini. Your mic starts automatically when it's your turn; just speak naturally and pause when you're done.
          </p>
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

export default BehavioralInterviewLive
