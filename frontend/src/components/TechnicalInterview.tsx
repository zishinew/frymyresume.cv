import { useState, useEffect, useRef } from 'react'
import Editor from '@monaco-editor/react' // Uncomment after: npm install @monaco-editor/react
import './TechnicalInterview.css'

interface TestResult {
  test_case: number
  input: any
  expected_output: any
  actual_output: any
  passed: boolean
  error?: string
}

interface Question {
  id: string
  title: string
  description: string
  difficulty: string
  examples: Array<{ input: string; output: string; explanation?: string }>
  constraints: string[]
  testCases: Array<{ input: any; expectedOutput: any }>
}

type Language = 'python' | 'javascript' | 'java' | 'cpp' | 'c'

interface TechnicalInterviewProps {
  company: string
  role: string
  difficulty: 'easy' | 'medium' | 'hard'
  onComplete: (score: number) => void
}

const LANGUAGE_OPTIONS: { value: Language; label: string; monacoLang: string }[] = [
  { value: 'python', label: 'Python3', monacoLang: 'python' },
  { value: 'javascript', label: 'JavaScript', monacoLang: 'javascript' },
  { value: 'java', label: 'Java', monacoLang: 'java' },
  { value: 'cpp', label: 'C++', monacoLang: 'cpp' },
  { value: 'c', label: 'C', monacoLang: 'c' },
]

function TechnicalInterview({ company, role, difficulty, onComplete }: TechnicalInterviewProps) {
  const [questions, setQuestions] = useState<Question[]>([])
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0)
  const [code, setCode] = useState<{ [key: string]: { [lang: string]: string } }>({})
  const [selectedLanguage, setSelectedLanguage] = useState<Language>('python')
  const [timeRemaining, setTimeRemaining] = useState(3600) // 60 minutes in seconds
  const [results, setResults] = useState<{ [key: string]: { passed: boolean; score: number; testResults?: TestResult[]; submitted?: boolean } }>({})
  const [loading, setLoading] = useState(false)
  const editorRef = useRef<any>(null)

  useEffect(() => {
    fetchQuestions()
    const timer = setInterval(() => {
      setTimeRemaining(prev => {
        if (prev <= 1) {
          handleSubmitAll()
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  const fetchQuestions = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/technical-questions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company, role, difficulty })
      })
      const data = await response.json()
      setQuestions(data.questions)
      // Initialize code for each question and language
      const initialCode: { [key: string]: { [lang: string]: string } } = {}
      data.questions.forEach((q: Question) => {
        initialCode[q.id] = {}
        LANGUAGE_OPTIONS.forEach(lang => {
          initialCode[q.id][lang.value] = getDefaultCode(q, lang.value)
        })
      })
      setCode(initialCode)
    } catch (error) {
      console.error('Error fetching questions:', error)
    }
  }

  const getDefaultCode = (question: Question, lang: Language): string => {
    // Generate appropriate template based on question
    const questionId = question?.id || ''
    
    const pythonTemplates: { [key: string]: string } = {
      'two-sum': `class Solution:
    def twoSum(self, nums: list[int], target: int) -> list[int]:
        # Your code here
        pass`,
      'reverse-string': `class Solution:
    def reverseString(self, s: list[str]) -> None:
        # Your code here
        pass`,
      'palindrome-number': `class Solution:
    def isPalindrome(self, x: int) -> bool:
        # Your code here
        return False`,
      'fizz-buzz': `class Solution:
    def fizzBuzz(self, n: int) -> list[str]:
        # Your code here
        return []`,
      'longest-substring': `class Solution:
    def lengthOfLongestSubstring(self, s: str) -> int:
        # Your code here
        return 0`,
      'valid-parentheses': `class Solution:
    def isValid(self, s: str) -> bool:
        # Your code here
        return False`,
      'group-anagrams': `class Solution:
    def groupAnagrams(self, strs: list[str]) -> list[list[str]]:
        # Your code here
        return []`,
      'product-except-self': `class Solution:
    def productExceptSelf(self, nums: list[int]) -> list[int]:
        # Your code here
        return []`,
      'merge-intervals': `class Solution:
    def merge(self, intervals: list[list[int]]) -> list[list[int]]:
        # Your code here
        return []`
    }

    const templates: { [key in Language]: string } = {
      python: pythonTemplates[questionId] || `class Solution:
    def solution(self, input):
        # Your code here
        return input`,
      javascript: `function solution(input) {
    // Your code here
    return input;
}`,
      java: `class Solution {
    public int solution(int[] input) {
        // Your code here
        return 0;
    }
}`,
      cpp: `class Solution {
public:
    int solution(vector<int>& input) {
        // Your code here
        return 0;
    }
};`,
      c: `int solution(int* input, int inputSize) {
    // Your code here
    return 0;
}`
    }
    return templates[lang]
  }

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const handleCopyCode = () => {
    const currentCode = code[questions[currentQuestionIndex]?.id]?.[selectedLanguage] || ''
    navigator.clipboard.writeText(currentCode)
    // Show temporary feedback
    const button = document.querySelector('.copy-button') as HTMLElement
    if (button) {
      const originalText = button.textContent
      button.textContent = 'Copied!'
      setTimeout(() => {
        if (button) button.textContent = originalText
      }, 2000)
    }
  }

  const handleRunCode = async (questionId: string) => {
    setLoading(true)
    // Clear previous results immediately
    setResults(prev => ({
      ...prev,
      [questionId]: {
        passed: false,
        score: 0,
        testResults: []
      }
    }))

    try {
      const currentCode = code[questionId]?.[selectedLanguage] || ''
      const response = await fetch('http://localhost:8000/api/run-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: currentCode,
          question_id: questionId,
          language: selectedLanguage,
          run_mode: 'run'  // Only run sample test cases
        })
      })
      const data = await response.json()
      setResults(prev => ({
        ...prev,
        [questionId]: {
          passed: data.passed || false,
          score: data.score || 0,
          testResults: data.test_results || []
        }
      }))
    } catch (error) {
      console.error('Error running code:', error)
      alert(`Error running code: ${error}. Make sure the backend is running on http://localhost:8000`)
      setResults(prev => ({
        ...prev,
        [questionId]: {
          passed: false,
          score: 0,
          testResults: []
        }
      }))
    } finally {
      setLoading(false)
    }
  }

  const handleSubmitQuestion = async (questionId: string) => {
    // Submit individual question (final submission with all test cases)
    setLoading(true)
    // Clear previous results immediately
    setResults(prev => ({
      ...prev,
      [questionId]: {
        passed: false,
        score: 0,
        testResults: []
      }
    }))

    try {
      const currentCode = code[questionId]?.[selectedLanguage] || ''
      const response = await fetch('http://localhost:8000/api/run-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: currentCode,
          question_id: questionId,
          language: selectedLanguage,
          run_mode: 'submit'  // Run ALL test cases including hidden ones
        })
      })
      const data = await response.json()
      setResults(prev => ({
        ...prev,
        [questionId]: {
          passed: data.passed || false,
          score: data.score || 0,
          testResults: data.test_results || [],
          submitted: true
        }
      }))
    } catch (error) {
      console.error('Error submitting code:', error)
      setResults(prev => ({
        ...prev,
        [questionId]: { 
          passed: false, 
          score: 0,
          submitted: true,
          testResults: []
        }
      }))
    } finally {
      setLoading(false)
    }
  }

  const handleSubmitAll = async () => {
    setLoading(true)
    let totalScore = 0
    for (const q of questions) {
      if (!results[q.id]) {
        await handleRunCode(q.id)
      }
      totalScore += results[q.id]?.score || 0
    }
    const averageScore = totalScore / questions.length
    onComplete(averageScore)
  }

  const handleEditorChange = (value: string | undefined) => {
    if (value !== undefined) {
      const questionId = questions[currentQuestionIndex]?.id
      if (questionId) {
        setCode(prev => ({
          ...prev,
          [questionId]: {
            ...prev[questionId],
            [selectedLanguage]: value
          }
        }))
      }
    }
  }

  const currentQuestion = questions[currentQuestionIndex]
  const currentCode = code[currentQuestion?.id]?.[selectedLanguage] || getDefaultCode(currentQuestion || {} as Question, selectedLanguage)

  if (questions.length === 0) {
    return <div className="technical-interview">Loading questions...</div>
  }

  return (
    <div className="technical-interview leetcode-style">
      <div className="interview-header">
        <div className="timer">
          <span className="timer-icon">⏱</span>
          {formatTime(timeRemaining)}
        </div>
        <div className="question-counter">
          Question {currentQuestionIndex + 1} of {questions.length}
        </div>
      </div>

      <div className="question-container">
        <div className="question-panel">
          <div className="question-header">
            <h2 className="question-title">{currentQuestion.title}</h2>
            <span className={`difficulty-badge ${currentQuestion.difficulty.toLowerCase()}`}>
              {currentQuestion.difficulty}
            </span>
          </div>
          <div className="question-description" dangerouslySetInnerHTML={{ __html: currentQuestion.description.replace(/\n/g, '<br/>') }} />
          
          <div className="examples-section">
            <h3 className="section-title">Examples:</h3>
            {currentQuestion.examples.map((example, idx) => (
              <div key={idx} className="example">
                <div className="example-label">Example {idx + 1}:</div>
                <div className="example-content">
                  <div className="example-input">
                    <strong>Input:</strong> <code>{example.input}</code>
                  </div>
                  <div className="example-output">
                    <strong>Output:</strong> <code>{example.output}</code>
                  </div>
                  {example.explanation && (
                    <div className="example-explanation">
                      <strong>Explanation:</strong> {example.explanation}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="constraints-section">
            <h3 className="section-title">Constraints:</h3>
            <ul>
              {currentQuestion.constraints.map((constraint, idx) => (
                <li key={idx}><code>{constraint}</code></li>
              ))}
            </ul>
          </div>
        </div>

        <div className="code-panel">
          <div className="code-editor-header">
            <div className="language-selector-wrapper">
              <select
                value={selectedLanguage}
                onChange={(e) => {
                  setSelectedLanguage(e.target.value as Language)
                  // Update editor content when language changes
                  const questionId = questions[currentQuestionIndex]?.id
                  if (questionId && editorRef.current) {
                    const newCode = code[questionId]?.[e.target.value as Language] || getDefaultCode(currentQuestion, e.target.value as Language)
                    editorRef.current.setValue(newCode)
                  }
                }}
                className="language-selector"
              >
                {LANGUAGE_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div className="code-actions">
              <button
                onClick={handleCopyCode}
                className="copy-button"
                title="Copy code"
              >
                📋 Copy
              </button>
              <button
                onClick={() => handleRunCode(currentQuestion.id)}
                disabled={loading}
                className="run-button"
              >
                {loading ? 'Running...' : '▶ Run'}
              </button>
              <button
                onClick={() => handleSubmitQuestion(currentQuestion.id)}
                disabled={loading}
                className="submit-button-header"
              >
                ✓ Submit
              </button>
            </div>
          </div>
          <div className="editor-wrapper">
            {/* Monaco Editor - Uncomment after installing @monaco-editor/react */}
            <Editor
              height="100%"
              language={LANGUAGE_OPTIONS.find(l => l.value === selectedLanguage)?.monacoLang || 'python'}
              value={currentCode}
              onChange={handleEditorChange}
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                automaticLayout: true,
                tabSize: 4,
                wordWrap: 'on',
                formatOnPaste: true,
                formatOnType: true,
              }}
              onMount={(editor) => {
                editorRef.current = editor
              }}
            />
          </div>
          {results[currentQuestion.id] && (
            <div className={`test-results ${results[currentQuestion.id].passed ? 'passed' : 'failed'}`}>
              <div className="result-header">
                {results[currentQuestion.id].passed ? (
                  <span className="result-icon success">✓</span>
                ) : (
                  <span className="result-icon error">✗</span>
                )}
                <span className="result-text">
                  {results[currentQuestion.id].passed
                    ? `Accepted`
                    : `Wrong Answer`}
                </span>
                <span className="result-score-inline">
                  {results[currentQuestion.id].testResults?.filter((t) => t.passed).length || 0} / {results[currentQuestion.id].testResults?.length || 0} test cases passed
                </span>
              </div>

              {/* Show all test case results */}
              {results[currentQuestion.id]?.testResults && results[currentQuestion.id]?.testResults.length > 0 && (
                <div className="test-cases-container">
                  <div className="test-cases-header">Test Cases:</div>
                  {results[currentQuestion.id].testResults?.map((test, idx) => (
                    <div key={idx} className={`test-case ${test.passed ? 'test-case-passed' : 'test-case-failed'}`}>
                      <div className="test-case-header">
                        <span className="test-case-number">Case {test.test_case}</span>
                        <span className={`test-case-status ${test.passed ? 'status-passed' : 'status-failed'}`}>
                          {test.passed ? '✓ Passed' : '✗ Failed'}
                        </span>
                      </div>
                      <div className="test-case-details">
                        <div className="test-input">
                          <strong>Input:</strong> <code>{JSON.stringify(test.input)}</code>
                        </div>
                        <div className="test-expected">
                          <strong>Expected:</strong> <code>{JSON.stringify(test.expected_output)}</code>
                        </div>
                        <div className="test-actual">
                          <strong>Output:</strong> <code className={test.passed ? 'output-correct' : 'output-wrong'}>
                            {test.error ? test.error : JSON.stringify(test.actual_output)}
                          </code>
                        </div>
                        {test.error && (
                          <div className="test-error">
                            <strong>Error:</strong> <span className="error-message">{test.error}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="result-summary">
                <span className="summary-label">Score:</span>
                <span className="summary-value">{results[currentQuestion.id]?.score ? results[currentQuestion.id].score.toFixed(1) : '0.0'}%</span>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="interview-navigation">
        <button
          onClick={() => setCurrentQuestionIndex(prev => Math.max(0, prev - 1))}
          disabled={currentQuestionIndex === 0}
          className="nav-button"
        >
          ← Previous
        </button>
        <div className="question-dots">
          {questions.map((_, idx) => (
            <button
              key={idx}
              onClick={() => setCurrentQuestionIndex(idx)}
              className={`dot ${idx === currentQuestionIndex ? 'active' : ''} ${results[questions[idx].id]?.passed ? 'completed' : ''}`}
              title={`Question ${idx + 1}`}
            />
          ))}
        </div>
        {currentQuestionIndex < questions.length - 1 ? (
          <button
            onClick={() => setCurrentQuestionIndex(prev => prev + 1)}
            className="nav-button"
          >
            Next →
          </button>
        ) : (
          <button
            onClick={handleSubmitAll}
            disabled={loading}
            className="submit-button"
          >
            {loading ? 'Submitting...' : 'Submit All'}
          </button>
        )}
      </div>
    </div>
  )
}

export default TechnicalInterview
