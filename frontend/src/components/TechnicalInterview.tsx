import { useState, useEffect, useRef } from 'react'
import Editor from '@monaco-editor/react' // Uncomment after: npm install @monaco-editor/react
import { API_BASE_URL } from '../config'
import './TechnicalInterview.css'

interface Question {
  id: string
  title: string
  difficulty: string
  description?: string
  examples?: Array<{ input: string; output: string; explanation?: string }>
  constraints?: string[]
}

interface GradeResult {
  passed: boolean
  score: number
  passed_tests: number
  total_tests: number
  test_results: Array<{
    test_case: number
    input: any
    expected_output: any
    actual_output: any
    passed: boolean
    error?: string | null
  }>
  is_efficient?: boolean
  efficiency_analysis?: {
    is_optimal: boolean
    actual_complexity: string
    optimal_complexity: string
    reasoning: string
  }
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
  const [solved, setSolved] = useState<Record<string, boolean>>({})

  const [loadingInterview, setLoadingInterview] = useState(true)
  const [gradingLoading, setGradingLoading] = useState(false)
  const [gradingErrorById, setGradingErrorById] = useState<Record<string, string | null>>({})
  const [gradeResultById, setGradeResultById] = useState<Record<string, GradeResult | null>>({})
  const [showSubmitModal, setShowSubmitModal] = useState(false)
  const [submitModalResult, setSubmitModalResult] = useState<GradeResult | null>(null)
  const [aiAnalysisLoading, setAiAnalysisLoading] = useState(false)

  const editorRef = useRef<any>(null)
  const questionsRef = useRef<Question[]>([])
  const solvedRef = useRef<Record<string, boolean>>({})
  const gradeResultByIdRef = useRef<Record<string, GradeResult | null>>({})

  useEffect(() => {
    solvedRef.current = solved
  }, [solved])

  useEffect(() => {
    questionsRef.current = questions
  }, [questions])

  useEffect(() => {
    gradeResultByIdRef.current = gradeResultById
  }, [gradeResultById])

  const getOrCreateClientId = (): string => {
    const key = 'offerready_client_id'
    try {
      const existing = localStorage.getItem(key)
      if (existing) return existing
      const generated = (globalThis.crypto && 'randomUUID' in globalThis.crypto)
        ? globalThis.crypto.randomUUID()
        : `client_${Math.random().toString(16).slice(2)}_${Date.now()}`
      localStorage.setItem(key, generated)
      return generated
    } catch {
      return `client_${Math.random().toString(16).slice(2)}_${Date.now()}`
    }
  }

  useEffect(() => {
    fetchQuestions()
    const timer = setInterval(() => {
      setTimeRemaining(prev => {
        if (prev <= 1) {
          finishRound()
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  // No generated prompts; hardcoded questions are returned directly.

  const fetchQuestions = async () => {
    try {
      setLoadingInterview(true)
      const client_id = getOrCreateClientId()
      const response = await fetch(`${API_BASE_URL}/api/technical-questions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company, role, difficulty, client_id })
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
    } finally {
      setLoadingInterview(false)
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
      'contains-duplicate': `class Solution:
    def hasDuplicate(self, nums: list[int]) -> bool:
        # Your code here
        return False`,
      'valid-anagram': `class Solution:
    def isAnagram(self, s: str, t: str) -> bool:
        # Your code here
        return False`,
      'valid-palindrome': `class Solution:
    def isPalindrome(self, s: str) -> bool:
        # Your code here
        return False`,
      'best-time-stock': `class Solution:
    def maxProfit(self, prices: list[int]) -> int:
        # Your code here
        return 0`,
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
      'longest-consecutive': `class Solution:
    def longestConsecutive(self, nums: list[int]) -> int:
        # Your code here
        return 0`,
      'three-sum': `class Solution:
    def threeSum(self, nums: list[int]) -> list[list[int]]:
        # Your code here
        return []`,
      'container-with-most-water': `class Solution:
    def maxArea(self, heights: list[int]) -> int:
        # Your code here
        return 0`,
      'find-min-rotated': `class Solution:
    def findMin(self, nums: list[int]) -> int:
        # Your code here
        return 0`,
      'group-anagrams': `class Solution:
    def groupAnagrams(self, strs: list[str]) -> list[list[str]]:
        # Your code here
        return []`,
      'top-k-frequent': `class Solution:
    def topKFrequent(self, nums: list[int], k: int) -> list[int]:
        # Your code here
        return []`,
      'minimum-window-substring': `class Solution:
    def minWindow(self, s: str, t: str) -> str:
        # Your code here
        return ""`,
      'reverse-linked-list': `# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next

class Solution:
    def reverseList(self, head):
        # Your code here
        return head`,
      'linked-list-cycle': `# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next

class Solution:
    def hasCycle(self, head) -> bool:
        # Your code here
        return False`,
      'reorder-list': `# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next

class Solution:
    def reorderList(self, head) -> None:
        # Your code here
        pass`,
      'merge-k-sorted-lists': `# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next

class Solution:
    def mergeKLists(self, lists):
        # Your code here
        return None`,
      'product-except-self': `class Solution:
    def productExceptSelf(self, nums: list[int]) -> list[int]:
        # Your code here
        return []`,
      'merge-intervals': `class Solution:
    def merge(self, intervals: list[list[int]]) -> list[list[int]]:
        # Your code here
        return []`
    }

    const javascriptTemplates: { [key: string]: string } = {
      'two-sum': `/**
 * @param {number[]} nums
 * @param {number} target
 * @return {number[]}
 */
function twoSum(nums, target) {
  // Your code here
  return [];
}`,
      'contains-duplicate': `/**
 * @param {number[]} nums
 * @return {boolean}
 */
function hasDuplicate(nums) {
  // Your code here
  return false;
}`,
      'valid-anagram': `/**
 * @param {string} s
 * @param {string} t
 * @return {boolean}
 */
function isAnagram(s, t) {
  // Your code here
  return false;
}`,
      'valid-palindrome': `/**
 * @param {string} s
 * @return {boolean}
 */
function isPalindrome(s) {
  // Your code here
  return false;
}`,
      'best-time-stock': `/**
 * @param {number[]} prices
 * @return {number}
 */
function maxProfit(prices) {
  // Your code here
  return 0;
}`,
      'group-anagrams': `/**
 * @param {string[]} strs
 * @return {string[][]}
 */
function groupAnagrams(strs) {
  // Your code here
  return [];
}`,
      'top-k-frequent': `/**
 * @param {number[]} nums
 * @param {number} k
 * @return {number[]}
 */
function topKFrequent(nums, k) {
  // Your code here
  return [];
}`,
      'longest-consecutive': `/**
 * @param {number[]} nums
 * @return {number}
 */
function longestConsecutive(nums) {
  // Your code here
  return 0;
}`,
      'three-sum': `/**
 * @param {number[]} nums
 * @return {number[][]}
 */
function threeSum(nums) {
  // Your code here
  return [];
}`,
      'container-with-most-water': `/**
 * @param {number[]} heights
 * @return {number}
 */
function maxArea(heights) {
  // Your code here
  return 0;
}`,
      'find-min-rotated': `/**
 * @param {number[]} nums
 * @return {number}
 */
function findMin(nums) {
  // Your code here
  return 0;
}`,
      'minimum-window-substring': `/**
 * @param {string} s
 * @param {string} t
 * @return {string}
 */
function minWindow(s, t) {
  // Your code here
  return "";
}`,
      'reverse-linked-list': `// Linked-list question: autograding is Python-only right now.
// Provided for convenience.
`,
      'linked-list-cycle': `// Linked-list question: autograding is Python-only right now.
// Provided for convenience.
`,
      'reorder-list': `// Linked-list question: autograding is Python-only right now.
// Provided for convenience.
`,
      'merge-k-sorted-lists': `// Linked-list question: autograding is Python-only right now.
// Provided for convenience.
`,
    }

    const javaTemplates: { [key: string]: string } = {
      'two-sum': `class Solution {
    public int[] twoSum(int[] nums, int target) {
        // Your code here
        return new int[0];
    }
}`,
      'contains-duplicate': `class Solution {
    public boolean hasDuplicate(int[] nums) {
        // Your code here
        return false;
    }
}`,
      'valid-anagram': `class Solution {
    public boolean isAnagram(String s, String t) {
        // Your code here
        return false;
    }
}`,
      'valid-palindrome': `class Solution {
    public boolean isPalindrome(String s) {
      // Your code here
      return false;
    }
  }`,
      'best-time-stock': `class Solution {
    public int maxProfit(int[] prices) {
      // Your code here
      return 0;
    }
  }`,
      'longest-consecutive': `import java.util.*;

  class Solution {
    public int longestConsecutive(int[] nums) {
      // Your code here
      return 0;
    }
  }`,
      'three-sum': `import java.util.*;

  class Solution {
    public List<List<Integer>> threeSum(int[] nums) {
      // Your code here
      return new ArrayList<>();
    }
  }`,
      'container-with-most-water': `class Solution {
    public int maxArea(int[] heights) {
      // Your code here
      return 0;
    }
  }`,
      'find-min-rotated': `class Solution {
    public int findMin(int[] nums) {
      // Your code here
      return 0;
    }
  }`,
      'group-anagrams': `import java.util.*;

class Solution {
    public List<List<String>> groupAnagrams(String[] strs) {
        // Your code here
        return new ArrayList<>();
    }
}`,
      'top-k-frequent': `class Solution {
    public int[] topKFrequent(int[] nums, int k) {
        // Your code here
        return new int[0];
    }
}`,
      'minimum-window-substring': `import java.util.*;

    class Solution {
        public String minWindow(String s, String t) {
        // Your code here
        return "";
        }
    }`,
      'reverse-linked-list': `// Linked-list question: autograding is Python-only right now.
    // Provided for convenience.
    `,
      'linked-list-cycle': `// Linked-list question: autograding is Python-only right now.
    // Provided for convenience.
    `,
      'reorder-list': `// Linked-list question: autograding is Python-only right now.
    // Provided for convenience.
    `,
      'merge-k-sorted-lists': `// Linked-list question: autograding is Python-only right now.
    // Provided for convenience.
    `,
    }

    const cppTemplates: { [key: string]: string } = {
      'two-sum': `#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    vector<int> twoSum(vector<int>& nums, int target) {
        // Your code here
        return {};
    }
};`,
      'contains-duplicate': `#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    bool hasDuplicate(vector<int>& nums) {
        // Your code here
        return false;
    }
};`,
      'valid-anagram': `#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    bool isAnagram(string s, string t) {
        // Your code here
        return false;
    }
};`,
      'valid-palindrome': `#include <bits/stdc++.h>
  using namespace std;

  class Solution {
  public:
    bool isPalindrome(string s) {
      // Your code here
      return false;
    }
  };`,
      'best-time-stock': `#include <bits/stdc++.h>
  using namespace std;

  class Solution {
  public:
    int maxProfit(vector<int>& prices) {
      // Your code here
      return 0;
    }
  };`,
      'longest-consecutive': `#include <bits/stdc++.h>
  using namespace std;

  class Solution {
  public:
    int longestConsecutive(vector<int>& nums) {
      // Your code here
      return 0;
    }
  };`,
      'three-sum': `#include <bits/stdc++.h>
  using namespace std;

  class Solution {
  public:
    vector<vector<int>> threeSum(vector<int>& nums) {
      // Your code here
      return {};
    }
  };`,
      'container-with-most-water': `#include <bits/stdc++.h>
  using namespace std;

  class Solution {
  public:
    int maxArea(vector<int>& heights) {
      // Your code here
      return 0;
    }
  };`,
      'find-min-rotated': `#include <bits/stdc++.h>
  using namespace std;

  class Solution {
  public:
    int findMin(vector<int>& nums) {
      // Your code here
      return 0;
    }
  };`,
      'group-anagrams': `#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    vector<vector<string>> groupAnagrams(vector<string>& strs) {
        // Your code here
        return {};
    }
};`,
      'top-k-frequent': `#include <bits/stdc++.h>
using namespace std;

class Solution {
public:
    vector<int> topKFrequent(vector<int>& nums, int k) {
        // Your code here
        return {};
    }
};`,
      'minimum-window-substring': `#include <bits/stdc++.h>
    using namespace std;

    class Solution {
    public:
        string minWindow(string s, string t) {
        // Your code here
        return "";
        }
    };`,
      'reverse-linked-list': `// Linked-list question: autograding is Python-only right now.
    // Provided for convenience.
    `,
      'linked-list-cycle': `// Linked-list question: autograding is Python-only right now.
    // Provided for convenience.
    `,
      'reorder-list': `// Linked-list question: autograding is Python-only right now.
    // Provided for convenience.
    `,
      'merge-k-sorted-lists': `// Linked-list question: autograding is Python-only right now.
    // Provided for convenience.
    `,
    }

    const cTemplates: { [key: string]: string } = {
      'two-sum': `// Note: In C, returning dynamic arrays requires manual allocation.
// This stub is illustrative; autograding supports Python/JavaScript only.
`,
      'contains-duplicate': `// Note: In C, sets/hashes require custom implementation.
// This stub is illustrative; autograding supports Python/JavaScript only.
`,
      'valid-anagram': `// Note: In C, strings are char arrays; sorting/counting requires manual work.
// This stub is illustrative; autograding supports Python/JavaScript only.
`,
      'valid-palindrome': `// Note: In C, you'd typically use two pointers and isalnum/tolower.
    // This stub is illustrative; autograding supports Python/JavaScript only.
    `,
      'best-time-stock': `// Note: In C, loop once tracking min and best profit.
    // This stub is illustrative; autograding supports Python/JavaScript only.
    `,
      'longest-consecutive': `// Note: In C, O(n) usually requires a hash set implementation.
    // This stub is illustrative; autograding supports Python/JavaScript only.
    `,
      'three-sum': `// Note: In C, sort + two pointers; returning 2D arrays requires manual allocation.
    // This stub is illustrative; autograding supports Python/JavaScript only.
    `,
      'container-with-most-water': `// Note: In C, two-pointer approach.
    // This stub is illustrative; autograding supports Python/JavaScript only.
    `,
      'find-min-rotated': `// Note: In C, binary search.
    // This stub is illustrative; autograding supports Python/JavaScript only.
    `,
      'group-anagrams': `// Note: In C, returning 2D arrays/strings requires manual allocation.
// This stub is illustrative; autograding supports Python/JavaScript only.
`,
      'top-k-frequent': `// Note: In C, heaps/maps require custom implementation.
// This stub is illustrative; autograding supports Python/JavaScript only.
`,
      'minimum-window-substring': `// Note: In C, sliding window with counts.
    // This stub is illustrative; autograding supports Python/JavaScript only.
    `,
      'reverse-linked-list': `// Linked-list question: autograding is Python-only right now.
    `,
      'linked-list-cycle': `// Linked-list question: autograding is Python-only right now.
    `,
      'reorder-list': `// Linked-list question: autograding is Python-only right now.
    `,
      'merge-k-sorted-lists': `// Linked-list question: autograding is Python-only right now.
    `,
    }

    const templates: { [key in Language]: string } = {
      python: pythonTemplates[questionId] || `class Solution:
    def solution(self, input):
        # input is a dict/object for generated problems
        # Your code here
        return None`,
      javascript: javascriptTemplates[questionId] || `function solution(input) {
    // Your code here
    return null;
}`,
      java: javaTemplates[questionId] || `class Solution {
    public int solution(int[] input) {
        // Your code here
        return 0;
    }
}`,
      cpp: cppTemplates[questionId] || `class Solution {
public:
    int solution(vector<int>& input) {
        // Your code here
        return 0;
    }
};`,
      c: cTemplates[questionId] || `int solution(int* input, int inputSize) {
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

  const gradeCurrent = async (mode: 'run' | 'submit') => {
    const q = questions[currentQuestionIndex]
    if (!q) return

    try {
      setGradingLoading(true)
      setGradingErrorById(prev => ({ ...prev, [q.id]: null }))

      // Show AI analysis loading for submit mode
      if (mode === 'submit') {
        setAiAnalysisLoading(true)
      }

      const currentCodeToRun = code[q.id]?.[selectedLanguage] || ''
      const response = await fetch(`${API_BASE_URL}/api/run-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: currentCodeToRun,
          question_id: q.id,
          language: selectedLanguage,
          run_mode: mode
        })
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data?.detail || 'Failed to grade')
      }
      setGradeResultById(prev => ({ ...prev, [q.id]: data }))

      if (mode === 'submit') {
        // Show overlay for submit results
        setSubmitModalResult(data)
        setShowSubmitModal(true)
        setTimeout(() => {
          setShowSubmitModal(false)
        }, 2500)
        if (data?.passed) {
          setSolved(prev => ({ ...prev, [q.id]: true }))
        }
      }
    } catch (e: any) {
      setGradingErrorById(prev => ({ ...prev, [q.id]: e?.message || 'Failed to grade' }))
    } finally {
      setGradingLoading(false)
      setAiAnalysisLoading(false)
    }
  }

  const finishRound = () => {
    const ids = questionsRef.current.map((q) => q.id)

    // Calculate total test cases passed across all questions
    let totalTestCasesPassed = 0
    let totalTestCasesAcrossAllQuestions = 0
    let inefficientCount = 0

    ids.forEach((id) => {
      const result = gradeResultByIdRef.current[id]
      if (result) {
        totalTestCasesPassed += result.passed_tests
        totalTestCasesAcrossAllQuestions += result.total_tests

        // Check if this question was inefficient
        if (result.is_efficient === false) {
          inefficientCount++
        }
      }
    })

    // Calculate base score: (total test cases passed / total test cases) * 100
    let baseScore = totalTestCasesAcrossAllQuestions > 0
      ? (totalTestCasesPassed / totalTestCasesAcrossAllQuestions) * 100
      : 0

    // Apply penalty based on number of inefficient solutions
    let penalty = 0
    if (inefficientCount === 1) {
      penalty = 20  // 20% penalty for one inefficient solution
    } else if (inefficientCount >= 2) {
      penalty = 30  // 30% penalty for both inefficient
    }

    // Final score = base score - penalty
    const finalScore = Math.max(0, baseScore - penalty)

    console.log(`Finish Round: ${totalTestCasesPassed}/${totalTestCasesAcrossAllQuestions} tests passed, inefficient count: ${inefficientCount}, base: ${baseScore}%, penalty: ${penalty}%, final: ${finalScore}%`)

    onComplete(finalScore)
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
  const gradeResult = currentQuestion ? gradeResultById[currentQuestion.id] : null
  const gradeError = currentQuestion ? gradingErrorById[currentQuestion.id] : null

  const jsUnsupportedFor = new Set([
    'reverse-linked-list',
    'linked-list-cycle',
    'reorder-list',
    'merge-k-sorted-lists'
  ])
  const autogradeSupported =
    selectedLanguage === 'python' ||
    (selectedLanguage === 'javascript' && !jsUnsupportedFor.has(currentQuestion?.id || ''))

  if (loadingInterview || questions.length === 0) {
    return (
      <div className="technical-loading-overlay">
        <div className="technical-loading-card">
          <div className="technical-loading-spinner" />
          <div className="technical-loading-title">Loading your technical interview…</div>
          <div className="technical-loading-subtitle">Loading questions and preparing the editor.</div>
        </div>
      </div>
    )
  }

  if (questions.length === 0) {
    return <div className="technical-interview">Loading questions...</div>
  }

  return (
    <div className="technical-interview leetcode-style">
      {/* AI Analysis Loading Overlay */}
      {aiAnalysisLoading && (
        <div className="submit-success-overlay" style={{ backgroundColor: 'rgba(10, 10, 10, 0.95)' }}>
          <div className="technical-loading-spinner" style={{ width: '60px', height: '60px' }} />
          <h2 className="submit-success-message" style={{ marginTop: '1.5rem' }}>
            Processing your answers...
          </h2>
          <p style={{ marginTop: '0.5rem', opacity: 0.7, fontSize: '0.9rem' }}>
            AI is analyzing time complexity
          </p>
        </div>
      )}

      {/* Submit Results Overlay */}
      {showSubmitModal && submitModalResult && !aiAnalysisLoading && (
        <div className="submit-success-overlay">
          <div className="submit-success-checkmark">✓</div>
          <h2 className="submit-success-message">
            {submitModalResult.passed ? 'All test cases passed!' : 'Some test cases failed'}
          </h2>
          <div style={{ marginTop: '1rem', fontSize: '1.5rem', fontWeight: 'bold' }}>
            Score: {submitModalResult.score}%
          </div>
          {submitModalResult.efficiency_analysis && (
            <div style={{ marginTop: '0.75rem', fontSize: '0.9rem', opacity: 0.85 }}>
              {submitModalResult.is_efficient
                ? '✓ Optimal time complexity'
                : `⚠ Suboptimal (${submitModalResult.efficiency_analysis.actual_complexity} vs ${submitModalResult.efficiency_analysis.optimal_complexity})`
              }
            </div>
          )}
        </div>
      )}

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
          </div>

          <div className="question-description">
            <div className="generated-prompt">{currentQuestion.description || ''}</div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginTop: '0.75rem' }}>
            <button className="run-button" onClick={() => gradeCurrent('run')} disabled={gradingLoading || !autogradeSupported}>
              {gradingLoading ? 'Running…' : 'Run'}
            </button>
            <button className="submit-button-header" onClick={() => gradeCurrent('submit')} disabled={gradingLoading || !autogradeSupported}>
              {gradingLoading ? 'Submitting…' : 'Submit'}
            </button>
          </div>

          {!autogradeSupported ? (
            <div style={{ marginTop: '0.5rem', opacity: 0.85, fontSize: '0.9rem' }}>
              Autograding currently supports Python and JavaScript only.
            </div>
          ) : null}

          {(currentQuestion.examples?.length ?? 0) > 0 ? (
            <div className="examples-section">
              <h3 className="section-title">Examples:</h3>
              {(currentQuestion.examples ?? []).slice(0, 3).map((ex, idx) => (
                <div className="example" key={idx}>
                  <div className="example-label">Example {idx + 1}</div>
                  <div className="example-content">
                    <div className="example-input">
                      <strong>Input:</strong>
                      <pre><code>{ex.input}</code></pre>
                    </div>
                    <div className="example-output">
                      <strong>Output:</strong>
                      <pre><code>{ex.output}</code></pre>
                    </div>
                    {ex.explanation && (
                      <div className="example-explanation">
                        <strong>Explanation:</strong> {ex.explanation}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          {(currentQuestion.constraints?.length ?? 0) > 0 ? (
            <div className="constraints-section">
              <h3 className="section-title">Constraints:</h3>
              <ul>
                {(currentQuestion.constraints ?? []).slice(0, 12).map((c, idx) => (
                  <li key={idx}>{c}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {null}
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
                onClick={() => gradeCurrent('run')}
                className="run-button"
                disabled={gradingLoading}
              >
                {gradingLoading ? 'Running…' : 'Run'}
              </button>
              <button
                onClick={() => gradeCurrent('submit')}
                className="submit-button-header"
                disabled={gradingLoading}
              >
                {gradingLoading ? 'Submitting…' : 'Submit'}
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

          {(gradeError || gradeResult) && (
            <div className={`test-results ${gradeResult?.passed ? 'passed' : 'failed'}`}>
              {gradeResult && (
                <>
                  <div className="result-summary">
                    <span className="summary-label">Passed:</span>
                    <span className="summary-value">
                      {gradeResult.passed_tests}/{gradeResult.total_tests}
                    </span>
                  </div>

                  <div className="test-cases-container">
                    <div className="test-cases-header">Test cases</div>
                    {gradeResult.test_results.slice(0, 12).map((tr) => (
                      <div
                        key={tr.test_case}
                        className={`test-case ${tr.passed ? 'test-case-passed' : 'test-case-failed'}`}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}>
                          <div style={{ fontWeight: 600 }}>
                            Test {tr.test_case}: {tr.passed ? 'Passed' : 'Failed'}
                          </div>
                          {tr.error && <div style={{ color: '#dc2626' }}>{tr.error}</div>}
                        </div>
                        <div style={{ marginTop: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                          <div><strong>Input:</strong> <code>{JSON.stringify(tr.input)}</code></div>
                          <div><strong>Expected:</strong> <code>{JSON.stringify(tr.expected_output)}</code></div>
                          <div><strong>Actual:</strong> <code>{JSON.stringify(tr.actual_output)}</code></div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
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
              className={`dot ${idx === currentQuestionIndex ? 'active' : ''} ${solved[questions[idx].id] ? 'completed' : ''}`}
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
            onClick={finishRound}
            className="submit-button"
          >
            Finish Round
          </button>
        )}
      </div>
    </div>
  )
}

export default TechnicalInterview
