export interface Job {
  id: string
  company: string
  role: string
  level: string
  type: 'intern'
  difficulty: 'easy' | 'medium' | 'hard'
  description: string
  location: string
}

export const jobs: Job[] = [
  // Easy - Startups
  {
    id: 'startup-1',
    company: 'TechFlow',
    role: 'Software Engineer Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'easy',
    description: 'Early-stage startup building AI-powered workflow tools',
    location: 'Remote'
  },
  {
    id: 'startup-2',
    company: 'DataVault',
    role: 'Full Stack Developer Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'easy',
    description: 'Fast-growing startup focused on data security solutions',
    location: 'San Francisco, CA'
  },
  {
    id: 'startup-3',
    company: 'CloudSync',
    role: 'Backend Engineer Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'easy',
    description: 'Innovative cloud infrastructure startup',
    location: 'Austin, TX'
  },

  // Medium - Mid-Tier Companies & Canadian Banks
  {
    id: 'intern-6',
    company: 'Shopify',
    role: 'Software Developer Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'medium',
    description: 'Shopify - Backend and full stack engineering internship',
    location: 'Ottawa, ON'
  },
  {
    id: 'intern-8',
    company: 'Stripe',
    role: 'Software Engineer Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'medium',
    description: 'Stripe - Payment platform internship',
    location: 'San Francisco, CA'
  },
  {
    id: 'intern-11',
    company: 'RBC',
    role: 'Software Developer Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'medium',
    description: 'Royal Bank of Canada - Tech and digital internship',
    location: 'Toronto, ON'
  },
  {
    id: 'intern-12',
    company: 'TD Bank',
    role: 'Software Engineer Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'medium',
    description: 'TD Bank - Digital solutions and backend internship',
    location: 'Toronto, ON'
  },

  // Hard - Big Tech Companies
  {
    id: 'intern-1',
    company: 'Google',
    role: 'Software Engineering Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'hard',
    description: 'Google - Cloud and search infrastructure internship',
    location: 'Mountain View, CA'
  },
  {
    id: 'intern-2',
    company: 'Amazon',
    role: 'SDE Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'hard',
    description: 'Amazon - Backend and AWS internship program',
    location: 'Seattle, WA'
  },
  {
    id: 'intern-3',
    company: 'Meta',
    role: 'Engineering Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'hard',
    description: 'Meta - Product engineering and infrastructure internship',
    location: 'Menlo Park, CA'
  },
  {
    id: 'intern-4',
    company: 'Microsoft',
    role: 'Software Engineer Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'hard',
    description: 'Microsoft - Cloud and productivity tools internship',
    location: 'Redmond, WA'
  },
  {
    id: 'intern-5',
    company: 'Apple',
    role: 'Software Engineer Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'hard',
    description: 'Apple - iOS and systems engineering internship',
    location: 'Cupertino, CA'
  },
  {
    id: 'intern-7',
    company: 'Netflix',
    role: 'Software Engineering Intern',
    level: 'Internship',
    type: 'intern',
    difficulty: 'hard',
    description: 'Netflix - Streaming platform internship',
    location: 'Los Gatos, CA'
  }
]

export const getJobsByType = (type: Job['type']) => {
  return jobs.filter(job => job.type === type)
}

export const getJobById = (id: string) => {
  return jobs.find(job => job.id === id)
}
