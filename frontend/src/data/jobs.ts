export interface Job {
  id: string
  company: string
  role: string
  level: string
  type: 'intern'
  difficulty: 'easy' | 'medium' | 'hard'
  description: string
  details: {
    about: string
    whatYoullDo: string[]
    minimumQualifications: string[]
  }
  location: string
}

export const jobs: Job[] = [
  // Easy - Entry-level friendly companies
  {
    id: 'startup-1',
    company: 'CodePath',
    role: 'Software Development Intern',
    level: 'Entry-level',
    type: 'intern',
    difficulty: 'easy',
    description: 'Non-profit tech training organization looking for teaching assistants',
    details: {
      about:
        'CodePath is a non-profit that provides free coding courses to college students. As a Software Development Intern/TA, you will help teach coding classes, assist students with debugging, and contribute to course materials.',
      whatYoullDo: [
        'Assist students during live coding sessions and office hours',
        'Help debug student code and explain fundamental programming concepts',
        'Review and provide feedback on student assignments',
        'Contribute to improving course curriculum and code examples',
      ],
      minimumQualifications: [
        'Completed at least one programming course (intro CS)',
        'Basic knowledge of one programming language (Python, Java, or JavaScript)',
        'Passion for helping others learn to code',
        'Good communication skills and patience',
      ],
    },
    location: 'Remote'
  },
  {
    id: 'startup-2',
    company: 'Local County IT',
    role: 'IT Support Intern',
    level: 'Entry-level',
    type: 'intern',
    difficulty: 'easy',
    description: 'County government office seeking tech-savvy interns',
    details: {
      about:
        'The County IT Department maintains technology systems for local government operations. You will help with basic website updates, troubleshoot employee tech issues, and assist with data entry and database maintenance.',
      whatYoullDo: [
        'Update content on county websites using CMS platforms',
        'Help employees with basic tech support (password resets, software issues)',
        'Assist with data entry and maintaining databases',
        'Document processes and create user guides',
      ],
      minimumQualifications: [
        'Basic understanding of computers and common software',
        'Willingness to learn HTML/CSS basics',
        'Good problem-solving and communication skills',
        'Attention to detail and organizational skills',
      ],
    },
    location: 'Various Locations'
  },
  {
    id: 'startup-3',
    company: 'University Research Lab',
    role: 'Research Assistant - Software',
    level: 'Entry-level',
    type: 'intern',
    difficulty: 'easy',
    description: 'Academic research lab seeking programming help for data analysis',
    details: {
      about:
        'Our research lab studies computational biology and needs help with data processing pipelines. You will write scripts to analyze research data, maintain existing code, and help visualize results.',
      whatYoullDo: [
        'Write Python scripts to process and clean research data',
        'Run existing analysis pipelines and document results',
        'Create basic visualizations and charts from data',
        'Help maintain lab codebases and documentation',
      ],
      minimumQualifications: [
        'Basic programming experience (Python preferred)',
        'Coursework in computer science or related field',
        'Ability to work independently and follow instructions',
        'Interest in research and data analysis',
      ],
    },
    location: 'On Campus'
  },

  // Medium - Mid-Tier Companies & Canadian Banks
  {
    id: 'intern-6',
    company: 'Shopify',
    role: 'Software Developer',
    level: 'Early Career',
    type: 'intern',
    difficulty: 'medium',
    description: 'Shopify - Backend and full stack product engineering',
    details: {
      about:
        'Join a product engineering team building commerce experiences used by millions of merchants. You will implement end-to-end features, write high-quality tests, and collaborate with engineers on performance, reliability, and developer experience.',
      whatYoullDo: [
        'Deliver user-facing product features with strong engineering quality',
        'Work across services, APIs, and UI depending on team needs',
        'Write tests, participate in reviews, and improve performance',
        'Partner with PM/design to scope and ship iteratively',
      ],
      minimumQualifications: [
        'Solid programming fundamentals (data structures, debugging, testing)',
        'Experience with web development (frontend or backend)',
        'Ability to communicate tradeoffs and collaborate in a team',
        'Comfort working with large codebases and incremental delivery',
      ],
    },
    location: 'Ottawa, ON'
  },
  {
    id: 'intern-8',
    company: 'Stripe',
    role: 'Software Engineer',
    level: 'Early Career',
    type: 'intern',
    difficulty: 'medium',
    description: 'Stripe - Payment platform engineering',
    details: {
      about:
        'Work on core payment flows and developer tooling that power internet businesses. You will build reliable services, improve APIs, and deliver polished experiences with careful attention to correctness and security.',
      whatYoullDo: [
        'Build and maintain reliable APIs and backend services',
        'Improve correctness, security, and observability of critical flows',
        'Collaborate on design docs and implement scoped improvements',
        'Write tests and contribute to operational excellence',
      ],
      minimumQualifications: [
        'Strong programming skills and attention to correctness',
        'Experience with service development and API design',
        'Comfort with testing, code reviews, and debugging',
        'Interest in security and reliability for production systems',
      ],
    },
    location: 'San Francisco, CA'
  },
  {
    id: 'intern-11',
    company: 'RBC',
    role: 'Software Developer',
    level: 'Early Career',
    type: 'intern',
    difficulty: 'medium',
    description: 'Royal Bank of Canada - Tech and digital engineering',
    details: {
      about:
        'Help build internal platforms and customer-facing digital products. You will work with modern engineering practices, contribute to secure service development, and collaborate across teams to deliver reliable experiences.',
      whatYoullDo: [
        'Build features for internal tools and customer-facing services',
        'Implement APIs and integrate with existing enterprise systems',
        'Write automated tests and improve monitoring/alerts',
        'Participate in design reviews and security best practices',
      ],
      minimumQualifications: [
        'Experience with application development and basic API concepts',
        'Comfort with CI/testing and structured development processes',
        'Strong communication and ability to work with stakeholders',
        'Interest in building secure, reliable systems',
      ],
    },
    location: 'Toronto, ON'
  },
  {
    id: 'intern-12',
    company: 'TD Bank',
    role: 'Software Engineer',
    level: 'Early Career',
    type: 'intern',
    difficulty: 'medium',
    description: 'TD Bank - Digital solutions and backend engineering',
    details: {
      about:
        'Build backend services and integrations for digital banking experiences. You will implement APIs, improve monitoring and quality, and work with stakeholders to ship features safely in a regulated environment.',
      whatYoullDo: [
        'Implement and maintain backend services and integrations',
        'Improve monitoring, logging, and operational readiness',
        'Write tests and help improve build/release quality',
        'Collaborate with cross-functional teams on requirements',
      ],
      minimumQualifications: [
        'Experience building backend services or APIs',
        'Familiarity with testing, version control, and code reviews',
        'Ability to work in a regulated/structured environment',
        'Strong fundamentals in debugging and problem-solving',
      ],
    },
    location: 'Toronto, ON'
  },

  // Hard - Big Tech Companies
  {
    id: 'intern-1',
    company: 'Google',
    role: 'Software Engineer',
    level: 'New Grad',
    type: 'intern',
    difficulty: 'hard',
    description: 'Google - Cloud and search infrastructure engineering',
    details: {
      about:
        'Work on large-scale systems that power cloud services and search infrastructure. You will tackle performance and reliability problems, implement production-quality code, and collaborate with engineers on design and testing.',
      whatYoullDo: [
        'Design and implement scalable services and infrastructure',
        'Analyze performance and reliability bottlenecks',
        'Write production code with strong tests and reviews',
        'Collaborate on system design and rollout plans',
      ],
      minimumQualifications: [
        'Strong CS fundamentals (data structures, algorithms, systems)',
        'Experience building and shipping software projects',
        'Comfort working with large codebases and design docs',
        'Ability to debug and optimize performance-critical code',
      ],
    },
    location: 'Mountain View, CA'
  },
  {
    id: 'intern-2',
    company: 'Amazon',
    role: 'Software Development Engineer',
    level: 'New Grad',
    type: 'intern',
    difficulty: 'hard',
    description: 'Amazon - Backend and AWS engineering',
    details: {
      about:
        'Build scalable backend services and internal tooling used across teams. You will write maintainable code, contribute to service design, and deliver measurable improvements in latency, availability, or customer experience.',
      whatYoullDo: [
        'Build and operate backend services with clear SLAs',
        'Own features from design to implementation and monitoring',
        'Improve latency, availability, and cost efficiency',
        'Write tests, dashboards, and runbooks for operations',
      ],
      minimumQualifications: [
        'Strong programming skills and CS fundamentals',
        'Experience with service development and distributed systems basics',
        'Comfort with operational ownership (monitoring, debugging)',
        'Ability to write high-quality, well-tested code',
      ],
    },
    location: 'Seattle, WA'
  },
  {
    id: 'intern-3',
    company: 'Meta',
    role: 'Software Engineer',
    level: 'New Grad',
    type: 'intern',
    difficulty: 'hard',
    description: 'Meta - Product engineering and infrastructure',
    details: {
      about:
        'Join a team building product features and the systems behind them. You will deliver end-to-end work, partner with cross-functional teams, and focus on performance, quality, and thoughtful user experiences.',
      whatYoullDo: [
        'Ship end-to-end product features and supporting services',
        'Measure impact with metrics and iterate based on data',
        'Improve performance and reliability across the stack',
        'Collaborate with PM/design/research on roadmap execution',
      ],
      minimumQualifications: [
        'Strong fundamentals in software engineering and problem-solving',
        'Experience building web/mobile/backend systems',
        'Comfort working with metrics, experimentation, and iteration',
        'Ability to collaborate in a fast-paced environment',
      ],
    },
    location: 'Menlo Park, CA'
  },
  {
    id: 'intern-4',
    company: 'Microsoft',
    role: 'Software Engineer',
    level: 'New Grad',
    type: 'intern',
    difficulty: 'hard',
    description: 'Microsoft - Cloud and productivity tools engineering',
    details: {
      about:
        'Contribute to cloud services and productivity products with a focus on engineering fundamentals. You will ship features, write tests, and collaborate through code reviews while learning at scale.',
      whatYoullDo: [
        'Build features for cloud services or productivity products',
        'Write and maintain automated tests and CI pipelines',
        'Collaborate via design reviews and code reviews',
        'Improve performance, accessibility, and reliability',
      ],
      minimumQualifications: [
        'Strong programming fundamentals and experience shipping projects',
        'Comfort with testing, code reviews, and iterative development',
        'Ability to work across teams and communicate clearly',
        'Interest in cloud systems or large-scale software products',
      ],
    },
    location: 'Redmond, WA'
  },
  {
    id: 'intern-5',
    company: 'Apple',
    role: 'Software Engineer',
    level: 'New Grad',
    type: 'intern',
    difficulty: 'hard',
    description: 'Apple - iOS and systems engineering',
    details: {
      about:
        'Work on user-facing experiences and the systems that support them. You will collaborate with engineers to build high-quality features, improve performance, and ship polished software with attention to detail.',
      whatYoullDo: [
        'Develop features with a strong focus on polish and quality',
        'Debug performance issues and optimize critical paths',
        'Collaborate with cross-functional partners (design, QA, PM)',
        'Write tests and maintain high engineering standards',
      ],
      minimumQualifications: [
        'Strong programming skills and attention to detail',
        'Experience with building user-facing apps or systems software',
        'Comfort with debugging tools and performance profiling',
        'Ability to write clean code and collaborate in reviews',
      ],
    },
    location: 'Cupertino, CA'
  },
  {
    id: 'intern-7',
    company: 'Netflix',
    role: 'Software Engineer',
    level: 'New Grad',
    type: 'intern',
    difficulty: 'hard',
    description: 'Netflix - Streaming platform engineering',
    details: {
      about:
        'Help build systems that support streaming experiences worldwide. You will work with modern tooling, focus on reliability and performance, and contribute features that improve developer or customer experience.',
      whatYoullDo: [
        'Build services and tooling supporting streaming experiences',
        'Improve reliability, performance, and observability',
        'Collaborate on incident reviews and operational improvements',
        'Ship well-tested code with clear ownership and documentation',
      ],
      minimumQualifications: [
        'Experience building backend systems and APIs',
        'Understanding of reliability/performance fundamentals',
        'Comfort with debugging and monitoring production systems',
        'Strong communication and ability to work cross-functionally',
      ],
    },
    location: 'Los Gatos, CA'
  }
]

export const getJobsByType = (type: Job['type']) => {
  return jobs.filter(job => job.type === type)
}

export const getJobById = (id: string) => {
  return jobs.find(job => job.id === id)
}
