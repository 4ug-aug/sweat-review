import { ModeToggle } from '@/components/mode-toggle'
import { ThemeProvider } from '@/components/theme-provider'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { HugeiconsIcon } from '@hugeicons/react'
import {
  ArrowRight01Icon,
  Cancel01Icon,
  CheckmarkCircle02Icon,
  Clock01Icon,
  ContainerIcon,
  Copy01Icon,
  GithubIcon,
  Globe02Icon,
  LockIcon,
  Rocket01Icon,
  ServerStack01Icon,
  Tick02Icon,
} from '@hugeicons/core-free-icons'
import { motion } from 'motion/react'
import React from 'react'


// ============================================================================
// STATIC DATA
// ============================================================================

const GITHUB_REPO_URL = 'https://github.com/4ug-aug/sweat-review'

const TERMINAL_LINES = [
  { prefix: '$', text: 'sweat-review start', color: 'text-muted-foreground' },
  { prefix: '●', text: 'Polling github.com/acme/app...', color: 'text-primary' },
  { prefix: '✓', text: 'PR #42 detected — cloning branch feature/auth', color: 'text-green-500' },
  { prefix: '✓', text: 'docker compose up -d --build', color: 'text-green-500' },
  { prefix: '✓', text: 'Preview live → pr42.10.0.1.4.nip.io', color: 'text-green-500' },
  { prefix: '●', text: 'Watching for changes...', color: 'text-primary' },
  { prefix: '✓', text: 'PR #42 updated — rebuilding...', color: 'text-green-500' },
  { prefix: '✓', text: 'PR #43 detected — deploying...', color: 'text-green-500' },
  { prefix: '✗', text: 'PR #42 closed — tearing down', color: 'text-red-500' },
]

const STATS = [
  { label: 'Fully Open Source', icon: GithubIcon },
  { label: 'Self-Hosted', icon: ServerStack01Icon },
  { label: '30s Poll Interval', icon: Clock01Icon },
  { label: 'Full Stack Isolation', icon: ContainerIcon },
]

const SAAS_ITEMS = [
  'Their cloud hosting',
  'They see your code',
  'Per-seat / per-preview pricing',
  'Secrets on their servers',
  'Vendor lock-in',
  'Requires public webhooks',
]

const AGENT_ITEMS = [
  'Your infrastructure',
  'Code never leaves your network',
  'Free forever (MIT)',
  'Secrets stay on your machine',
  'None — it\'s a Python script',
  'Works behind NAT/firewalls',
]

const QUICK_START_STEPS = [
  {
    number: 1,
    title: 'Initialize',
    code: `uvx sweat-review init
# Prompts for GitHub token, repo, and VPS IP
# Sets up .env and starts Traefik automatically`,
  },
  {
    number: 2,
    title: 'Start',
    code: `uvx sweat-review start`,
  },
]


// ============================================================================
// GRILL SEPARATOR
// ============================================================================

const GrillSeparator = () => (
  <div className="h-12 w-full border-y border-border bg-[linear-gradient(to_right,transparent_calc(100%-1px),var(--border)_calc(100%-1px))] bg-[length:12px_100%]" />
)


// ============================================================================
// ANIMATED TERMINAL
// ============================================================================

const AnimatedTerminal = () => {
  const [visibleLines, setVisibleLines] = React.useState(0)
  const [cycle, setCycle] = React.useState(0)

  React.useEffect(() => {
    if (visibleLines < TERMINAL_LINES.length) {
      const timeout = setTimeout(() => {
        setVisibleLines(prev => prev + 1)
      }, visibleLines === 0 ? 600 : 400 + Math.random() * 300)
      return () => clearTimeout(timeout)
    } else {
      const timeout = setTimeout(() => {
        setVisibleLines(0)
        setCycle(prev => prev + 1)
      }, 3000)
      return () => clearTimeout(timeout)
    }
  }, [visibleLines])

  return (
    <div className="rounded-lg border border-border bg-[#0d1117] dark:bg-[#0a0a0a] overflow-hidden shadow-2xl">
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/10">
        <div className="w-3 h-3 rounded-full bg-red-500/80" />
        <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
        <div className="w-3 h-3 rounded-full bg-green-500/80" />
        <span className="ml-2 text-xs text-white/40 font-mono">terminal</span>
      </div>
      {/* Content */}
      <div className="p-4 font-mono text-sm leading-relaxed min-h-[280px]">
        {TERMINAL_LINES.slice(0, visibleLines).map((line, i) => (
          <motion.div
            key={`${cycle}-${i}`}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="flex gap-2"
          >
            <span className={cn('shrink-0', line.color === 'text-muted-foreground' ? 'text-gray-500' : line.color === 'text-primary' ? 'text-blue-400' : line.color === 'text-green-500' ? 'text-green-400' : 'text-red-400')}>
              {line.prefix}
            </span>
            <span className="text-gray-300">{line.text}</span>
          </motion.div>
        ))}
        {visibleLines < TERMINAL_LINES.length && (
          <motion.span
            animate={{ opacity: [1, 0] }}
            transition={{ duration: 0.8, repeat: Infinity }}
            className="inline-block w-2 h-4 bg-gray-400 ml-0.5"
          />
        )}
      </div>
    </div>
  )
}


// ============================================================================
// PR LIFECYCLE CARD (animated status badges)
// ============================================================================

const PRLifecycleCard = ({ prNumber, branch, statusSequence, delay }: {
  prNumber: number
  branch: string
  statusSequence: { label: string; color: string; bgColor: string }[]
  delay: number
}) => {
  const [statusIndex, setStatusIndex] = React.useState(0)

  React.useEffect(() => {
    if (statusSequence.length <= 1) return

    const interval = setInterval(() => {
      setStatusIndex(prev => (prev + 1) % statusSequence.length)
    }, 3000 + delay)

    return () => clearInterval(interval)
  }, [statusSequence.length, delay])

  const status = statusSequence[statusIndex]

  return (
    <div className="flex-1 min-w-[140px] rounded-md border border-border bg-background/50 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-bold text-foreground">#{prNumber}</span>
        <motion.div
          key={status.label}
          initial={{ y: 8, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ type: 'spring', damping: 15, stiffness: 300 }}
        >
          <Badge className={cn('border font-semibold px-2 py-0 h-5 text-[10px]', status.color, status.bgColor)}>
            {status.label}
          </Badge>
        </motion.div>
      </div>
      <p className="text-xs text-muted-foreground font-mono truncate">{branch}</p>
    </div>
  )
}


// ============================================================================
// BENTO GRID
// ============================================================================

const BentoGrid = ({ children }: { children: React.ReactNode }) => (
  <div className="grid grid-cols-1 md:grid-cols-3 gap-0 border-collapse">
    {children}
  </div>
)

const BentoCell = ({
  children,
  className,
  title,
  description,
  span = 1
}: {
  children: React.ReactNode
  className?: string
  title: string
  description: string
  span?: 1 | 2
}) => (
  <div className={cn(
    "flex flex-col border-r border-b border-border p-5",
    span === 2 ? "md:col-span-2" : "md:col-span-1",
    className
  )}>
    <div className="mb-4">
      <h3 className="text-lg font-bold text-foreground mb-1">{title}</h3>
      <p className="text-xs text-muted-foreground leading-relaxed max-w-sm">
        {description}
      </p>
    </div>
    <div className="flex-1 min-h-[180px] flex items-center justify-center overflow-hidden">
      {children}
    </div>
  </div>
)


// ============================================================================
// HEADER
// ============================================================================

const Header = () => {
  const navLinks = [
    { label: 'Built For', href: '#built-for' },
    { label: 'How it Works', href: '#how-it-works' },
    { label: 'Why Self-Hosted', href: '#why-self-hosted' },
    { label: 'Quick Start', href: '#quick-start' },
  ]

  return (
    <header className="sticky top-0 z-50 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <a href="/" className="flex items-center gap-2">
          <img src="/sweat-review.svg" alt="SWEAT" className="h-8 w-auto invert dark:invert-0" />
          <span className="font-semibold text-foreground tracking-tight">SWEAT Review</span>
        </a>

        <nav className="hidden md:flex items-center gap-8">
          {navLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <a href={GITHUB_REPO_URL} target="_blank" rel="noopener noreferrer">
            <Button variant="outline" size="sm" className="gap-2 h-8">
              <HugeiconsIcon icon={GithubIcon} className="h-4 w-4" />
              <span className="hidden sm:inline">Star on GitHub</span>
            </Button>
          </a>
          <ModeToggle />
        </div>
      </div>
    </header>
  )
}


// ============================================================================
// HERO SECTION
// ============================================================================

const HeroSection = () => {
  return (
    <section className="relative pt-24 pb-20 overflow-hidden">
      <div className="relative z-10 max-w-7xl mx-auto px-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          {/* Left Side */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            className="text-left"
          >
            <Badge variant="outline" className="mb-6 gap-1.5 px-3 py-1 h-auto">
              <HugeiconsIcon icon={GithubIcon} className="h-3.5 w-3.5" />
              100% Open Source · MIT Licensed
            </Badge>

            <h1 className="text-5xl md:text-6xl lg:text-7xl font-extrabold leading-[1.05] tracking-tight text-foreground mb-8">
              Self-Hosted Preview{' '}
              <br className="hidden md:block" />
              Environments{' '}
              <br className="hidden md:block" />
              <span className="bg-gradient-to-r from-primary via-chart-1 to-chart-4 bg-clip-text text-transparent">
                on Autopilot.
              </span>
            </h1>

            <p className="text-xl md:text-2xl text-muted-foreground mb-10 max-w-xl">
              Open a PR, get a preview URL. Close it, it's gone.{' '}
              <span className="text-primary">No PaaS, no webhooks, no CI pipeline — just your VPS and a compose file.</span>
            </p>

            <div className="flex flex-wrap gap-4 mb-12">
              <a href={GITHUB_REPO_URL} target="_blank" rel="noopener noreferrer">
                <Button className="gap-2">
                  <HugeiconsIcon icon={GithubIcon} className="h-5 w-5" />
                  View on GitHub
                </Button>
              </a>
              <a href="#quick-start">
                <Button variant="outline" className="gap-2">
                  <HugeiconsIcon icon={Rocket01Icon} className="h-5 w-5" />
                  Quick Start
                </Button>
              </a>
            </div>

            {/* Stats row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 pt-8 border-t border-border/40">
              {STATS.map((stat) => (
                <div key={stat.label} className="flex items-center gap-2">
                  <HugeiconsIcon icon={stat.icon} className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-xs font-semibold text-foreground">{stat.label}</span>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Right Side: Animated Terminal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.2, ease: 'easeOut' }}
          >
            <AnimatedTerminal />
          </motion.div>
        </div>
      </div>
    </section>
  )
}


// ============================================================================
// BUILT FOR SECTION
// ============================================================================

const BUILT_FOR_ITEMS = [
  'You deploy with Docker Compose and want preview URLs per PR',
  'You run on a single VPS, mini PC, or home server - not Kubernetes',
  'You want previews without adopting a PaaS or configuring CI pipelines',
  'You use AI agents to open PRs and need to review what they built',
]

const BuiltForSection = () => (
  <section id="built-for">
    <div className="py-14 px-6 text-center border-b border-border">
      <h2 className="text-3xl font-extrabold text-foreground tracking-tight mb-4">
        Built For
      </h2>
      <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
        SWEAT Review is not a PaaS. It does one thing for a specific kind of setup.
      </p>
    </div>
    <div className="p-6 md:p-10 flex flex-col items-center">
      <div className="space-y-3">
        {BUILT_FOR_ITEMS.map((item, i) => (
          <div key={i} className="flex items-start gap-3 text-left">
            <div className="flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 border border-primary/20 text-primary shrink-0 mt-0.5">
              <HugeiconsIcon icon={Tick02Icon} className="w-3 h-3" />
            </div>
            <span className="text-sm text-foreground/90">{item}</span>
          </div>
        ))}
      </div>
    </div>
  </section>
)


// ============================================================================
// HOW IT WORKS SECTION
// ============================================================================

const MockEnvFile = () => (
  <div className="w-full rounded-md border border-border bg-[#0d1117] dark:bg-[#0a0a0a] overflow-hidden">
    <div className="px-3 py-1.5 border-b border-white/10 flex items-center gap-2">
      <span className="text-[10px] text-white/40 font-mono">.env</span>
    </div>
    <div className="p-3 font-mono text-xs leading-relaxed">
      {[
        { key: 'GITHUB_TOKEN', value: 'ghp_••••••' },
        { key: 'GITHUB_REPO', value: 'acme/app' },
        { key: 'VPS_IP', value: '10.0.1.4' },
        { key: 'TRIGGER_LABEL', value: 'preview' },
      ].map((line) => (
        <div key={line.key}>
          <span className="text-gray-500">{line.key}</span>
          <span className="text-gray-600">=</span>
          <span className="text-chart-1">{line.value}</span>
        </div>
      ))}
    </div>
  </div>
)

const MiniStack = ({ label }: { label: string }) => (
  <div className="flex-1 min-w-[80px]">
    <div className="text-[10px] font-bold text-foreground mb-1.5 text-center">{label}</div>
    <div className="rounded border border-border overflow-hidden">
      {['frontend', 'backend', 'db'].map((svc, i) => (
        <div
          key={svc}
          className={cn(
            'text-[9px] text-center py-1.5 font-mono',
            i === 0 ? 'bg-chart-1/15 text-chart-1' :
            i === 1 ? 'bg-chart-3/15 text-chart-3' :
            'bg-chart-5/15 text-chart-5',
            i < 2 && 'border-b border-border'
          )}
        >
          {svc}
        </div>
      ))}
    </div>
  </div>
)

const TraefikDiagram = () => (
  <div className="w-full space-y-2.5">
    {[42, 43, 44, 45].map((pr) => (
      <div key={pr} className="flex items-center gap-2 text-xs">
        <div className="flex-1 rounded border border-border px-2 py-1.5 font-mono text-[10px] text-muted-foreground truncate bg-muted/20">
          pr{pr}.10.0.1.4.nip.io
        </div>
        <HugeiconsIcon icon={ArrowRight01Icon} className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <div className="rounded border border-chart-4/40 bg-chart-4/10 px-2 py-1.5 text-[10px] font-bold text-chart-4 shrink-0">
          Traefik
        </div>
        <HugeiconsIcon icon={ArrowRight01Icon} className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <div className="rounded border border-chart-3/40 bg-chart-3/10 px-2 py-1.5 text-[10px] font-bold text-chart-3 shrink-0">
          PR #{pr}
        </div>
      </div>
    ))}
  </div>
)

const HowItWorksSection = () => {
  return (
    <section id="how-it-works">
      <div className="py-12 px-6 text-center border-b border-border">
        <h2 className="text-3xl font-extrabold text-foreground tracking-tight mb-4">
          How It Works
        </h2>
        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
          Polls the GitHub API — no webhooks, no CI, no DNS config. Works behind NAT and firewalls.
        </p>
      </div>
      <BentoGrid>
        <BentoCell
          title="PR Lifecycle"
          description="The agent watches your repo, deploys on open, rebuilds on push, tears down on close."
          span={2}
        >
          <div className="flex gap-3 w-full">
            <PRLifecycleCard
              prNumber={42}
              branch="feat/auth"
              delay={0}
              statusSequence={[
                { label: 'Deploying', color: 'text-chart-1', bgColor: 'border-chart-1/50 bg-chart-1/10' },
                { label: 'Live', color: 'text-chart-4', bgColor: 'border-chart-4/50 bg-chart-4/10' },
              ]}
            />
            <PRLifecycleCard
              prNumber={43}
              branch="fix/dashboard"
              delay={1000}
              statusSequence={[
                { label: 'Building', color: 'text-chart-2', bgColor: 'border-chart-2/50 bg-chart-2/10' },
                { label: 'Live', color: 'text-chart-4', bgColor: 'border-chart-4/50 bg-chart-4/10' },
              ]}
            />
            <PRLifecycleCard
              prNumber={44}
              branch="chore/deps"
              delay={0}
              statusSequence={[
                { label: 'Torn Down', color: 'text-muted-foreground', bgColor: 'border-border bg-muted/20' },
              ]}
            />
          </div>
        </BentoCell>

        <BentoCell
          title="Your Machine, Your Rules"
          description="No SaaS dashboard. No vendor API keys. Gate previews to a label or deploy all PRs — your call."
        >
          <MockEnvFile />
        </BentoCell>

        <BentoCell
          title="Full Stack Isolation"
          description="Each PR gets its own complete Docker Compose stack — frontend, backend, database, workers."
        >
          <div className="flex gap-3 w-full">
            <MiniStack label="PR #1" />
            <MiniStack label="PR #2" />
            <MiniStack label="PR #3" />
          </div>
        </BentoCell>

        <BentoCell
          title="Traefik Routing"
          description="Automatic subdomain routing via Traefik. No domain registration needed thanks to nip.io."
          span={2}
          className="border-b-0"
        >
          <TraefikDiagram />
        </BentoCell>
      </BentoGrid>
    </section>
  )
}


// ============================================================================
// WHY SELF-HOSTED SECTION
// ============================================================================

const ComparisonCard = ({
  title,
  items,
  variant,
}: {
  title: string
  items: string[]
  variant: 'saas' | 'agent'
}) => {
  const isSaas = variant === 'saas'

  return (
    <div className={cn(
      "flex-1 rounded-lg border p-6 transition-all",
      isSaas
        ? "opacity-75 grayscale-[0.3] border-border bg-muted/5"
        : "border-primary/20 bg-primary/5 shadow-lg shadow-primary/5"
    )}>
      <div className="flex items-center gap-2 mb-6">
        {isSaas ? (
          <Badge variant="outline" className="text-muted-foreground border-border bg-muted/20">
            The Old Way
          </Badge>
        ) : (
          <Badge className="bg-primary/10 text-primary border-primary/20">
            SWEAT Review
          </Badge>
        )}
      </div>
      <h3 className={cn(
        "text-lg font-bold mb-4",
        isSaas ? "text-muted-foreground" : "text-foreground"
      )}>
        {title}
      </h3>
      <div className="space-y-3">
        {items.map((item, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className={cn(
              "flex items-center justify-center w-5 h-5 rounded-full shrink-0 border",
              isSaas
                ? "bg-muted/10 border-muted text-muted-foreground/50"
                : "bg-green-500/10 border-green-500/20 text-green-600 dark:text-green-400"
            )}>
              <HugeiconsIcon
                icon={isSaas ? Cancel01Icon : Tick02Icon}
                className="w-3 h-3"
              />
            </div>
            <span className={cn(
              "text-sm",
              isSaas ? "text-muted-foreground/70" : "text-foreground/90"
            )}>
              {item}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

const WhySelfHostedSection = () => {
  return (
    <section id="why-self-hosted">
      <div className="py-14 px-6 text-center border-b border-border">
        <h2 className="text-3xl font-extrabold text-foreground tracking-tight mb-4">
          No SaaS. No Surprises.
        </h2>
        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
          Preview environments without the platform tax.
        </p>
      </div>
      <div className="p-6 md:p-10">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ComparisonCard
            title="SaaS Preview Tools"
            items={SAAS_ITEMS}
            variant="saas"
          />
          <ComparisonCard
            title="SWEAT Review"
            items={AGENT_ITEMS}
            variant="agent"
          />
        </div>
      </div>
    </section>
  )
}


// ============================================================================
// COMPARISON TABLE SECTION
// ============================================================================

const COMPARISON_FEATURES = [
  'Self-hosted',
  'Open source',
  'Full-stack previews',
  'No vendor lock-in',
  'Works behind NAT',
  'Free',
  'No config changes to your repo',
  'Database included',
]

const COMPARISON_TOOLS: {
  name: string
  category: string
  features: Record<string, boolean | string>
  highlight?: boolean
}[] = [
  {
    name: 'SWEAT Review',
    category: 'Self-hosted agent',
    highlight: true,
    features: {
      'Self-hosted': true,
      'Open source': true,
      'Full-stack previews': true,
      'No vendor lock-in': true,
      'Works behind NAT': true,
      'Free': true,
      'No config changes to your repo': true,
      'Database included': true,
    },
  },
  {
    name: 'Vercel Previews',
    category: 'SaaS',
    features: {
      'Self-hosted': false,
      'Open source': false,
      'Full-stack previews': false,
      'No vendor lock-in': false,
      'Works behind NAT': true,
      'Free': false,
      'No config changes to your repo': false,
      'Database included': false,
    },
  },
  {
    name: 'Netlify Deploy Previews',
    category: 'SaaS',
    features: {
      'Self-hosted': false,
      'Open source': false,
      'Full-stack previews': false,
      'No vendor lock-in': false,
      'Works behind NAT': true,
      'Free': false,
      'No config changes to your repo': false,
      'Database included': false,
    },
  },
  {
    name: 'PullPreview',
    category: 'Preview tool',
    features: {
      'Self-hosted': true,
      'Open source': true,
      'Full-stack previews': true,
      'No vendor lock-in': true,
      'Works behind NAT': false,
      'Free': true,
      'No config changes to your repo': false,
      'Database included': true,
    },
  },
  {
    name: 'Coolify',
    category: 'PaaS',
    features: {
      'Self-hosted': true,
      'Open source': true,
      'Full-stack previews': true,
      'No vendor lock-in': true,
      'Works behind NAT': false,
      'Free': true,
      'No config changes to your repo': false,
      'Database included': true,
    },
  },
  {
    name: 'Railway',
    category: 'PaaS',
    features: {
      'Self-hosted': false,
      'Open source': false,
      'Full-stack previews': true,
      'No vendor lock-in': false,
      'Works behind NAT': true,
      'Free': false,
      'No config changes to your repo': false,
      'Database included': true,
    },
  },
]

const ComparisonSection = () => {
  return (
    <section id="comparison">
      <div className="py-14 px-6 text-center border-b border-border">
        <h2 className="text-3xl font-extrabold text-foreground tracking-tight mb-4">
          Different Tools, Different Jobs
        </h2>
        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
          PaaS platforms do a hundred things. SWEAT Review does one — PR previews for Docker Compose projects on your own server.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left p-4 font-medium text-muted-foreground min-w-[180px]">
                Feature
              </th>
              {COMPARISON_TOOLS.map((tool) => (
                <th
                  key={tool.name}
                  className={cn(
                    'p-4 text-center min-w-[120px]',
                    tool.highlight && 'bg-primary/5'
                  )}
                >
                  <div className={cn(
                    'font-bold text-sm',
                    tool.highlight ? 'text-primary' : 'text-foreground'
                  )}>
                    {tool.name}
                  </div>
                  <div className="text-[10px] text-muted-foreground font-normal mt-0.5">
                    {tool.category}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {COMPARISON_FEATURES.map((feature, i) => (
              <tr
                key={feature}
                className={cn(
                  'border-b border-border/50',
                  i % 2 === 0 && 'bg-muted/5'
                )}
              >
                <td className="p-4 text-foreground font-medium text-xs">
                  {feature}
                </td>
                {COMPARISON_TOOLS.map((tool) => {
                  const value = tool.features[feature]
                  return (
                    <td
                      key={tool.name}
                      className={cn(
                        'p-4 text-center',
                        tool.highlight && 'bg-primary/5'
                      )}
                    >
                      {typeof value === 'string' ? (
                        <span className="text-xs text-muted-foreground">{value}</span>
                      ) : value ? (
                        <HugeiconsIcon
                          icon={Tick02Icon}
                          className="h-4 w-4 text-green-600 dark:text-green-400 mx-auto"
                        />
                      ) : (
                        <HugeiconsIcon
                          icon={Cancel01Icon}
                          className="h-4 w-4 text-muted-foreground/30 mx-auto"
                        />
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}


// ============================================================================
// QUICK START SECTION
// ============================================================================

const CodeBlock = ({ code }: { code: string }) => {
  const [copied, setCopied] = React.useState(false)

  const copyToClipboard = () => {
    const commands = code
      .split('\n')
      .filter(line => !line.startsWith('#') && line.trim() !== '')
      .join('\n')
    navigator.clipboard.writeText(commands)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="group relative rounded-md border border-border bg-[#0d1117] dark:bg-[#0a0a0a] overflow-hidden">
      <button
        onClick={copyToClipboard}
        className="absolute top-2.5 right-2.5 p-1.5 rounded-md bg-white/5 border border-white/10 text-gray-500 hover:text-gray-300 hover:bg-white/10 transition-all opacity-0 group-hover:opacity-100"
      >
        <HugeiconsIcon
          icon={copied ? CheckmarkCircle02Icon : Copy01Icon}
          className={cn('h-3.5 w-3.5', copied && 'text-green-400')}
        />
      </button>
      <pre className="p-4 font-mono text-xs leading-relaxed text-gray-300 overflow-x-auto">
        {code.split('\n').map((line, i) => (
          <div key={i}>
            {line.startsWith('#') ? (
              <span className="text-gray-600">{line}</span>
            ) : (
              line
            )}
          </div>
        ))}
      </pre>
    </div>
  )
}

const QuickStartSection = () => {
  return (
    <section id="quick-start">
      <div className="py-14 px-6 text-center border-b border-border">
        <h2 className="text-3xl font-extrabold text-foreground tracking-tight mb-4">
          Up and Running in 60 Seconds
        </h2>
        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
          Your docker-compose.yml is the only config we need.
        </p>
      </div>
      <div className="p-6 md:p-10 space-y-8 max-w-2xl mx-auto">
        {QUICK_START_STEPS.map((step) => (
          <div key={step.number}>
            <div className="flex items-center gap-3 mb-3">
              <div className="flex items-center justify-center w-7 h-7 rounded-full bg-primary/10 border border-primary/20 text-primary font-bold text-sm shrink-0">
                {step.number}
              </div>
              <h3 className="text-base font-bold text-foreground">{step.title}</h3>
            </div>
            <CodeBlock code={step.code} />
          </div>
        ))}
      </div>
    </section>
  )
}


// ============================================================================
// FOOTER
// ============================================================================

const FooterSection = () => {
  return (
    <footer className="bg-background">
      <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-border">
        <div className="p-8 flex items-center justify-center md:justify-start">
          <a href="/" className="flex items-center gap-2">
            <img src="/sweat-review.svg" alt="SWEAT" className="h-8 w-auto invert dark:invert-0" />
            <span className="font-bold text-foreground">SWEAT Review</span>
          </a>
        </div>
        <div className="p-8 flex items-center justify-center gap-8">
          <a href={GITHUB_REPO_URL} target="_blank" rel="noopener noreferrer" className="text-sm text-muted-foreground hover:text-foreground transition-colors font-medium flex items-center gap-1.5">
            <HugeiconsIcon icon={GithubIcon} className="h-4 w-4" />
            GitHub
          </a>
          <a href={`${GITHUB_REPO_URL}#readme`} target="_blank" rel="noopener noreferrer" className="text-sm text-muted-foreground hover:text-foreground transition-colors font-medium flex items-center gap-1.5">
            <HugeiconsIcon icon={Globe02Icon} className="h-4 w-4" />
            Documentation
          </a>
        </div>
        <div className="p-8 flex items-center justify-center md:justify-end gap-2 text-xs text-muted-foreground font-medium">
          <HugeiconsIcon icon={LockIcon} className="h-3.5 w-3.5" />
          Open Source Forever — MIT License
        </div>
      </div>
    </footer>
  )
}


// ============================================================================
// APP
// ============================================================================

const App = () => {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
      <div className="max-w-5xl mx-auto border-x border-border">
        <Header />
        <div className="relative z-10 flex flex-col">
          <HeroSection />
          <GrillSeparator />
          <BuiltForSection />
          <GrillSeparator />
          <HowItWorksSection />
          <GrillSeparator />
          <WhySelfHostedSection />
          <GrillSeparator />
          <ComparisonSection />
          <GrillSeparator />
          <QuickStartSection />
          <GrillSeparator />
          <FooterSection />
        </div>
      </div>
    </ThemeProvider>
  )
}

export default App
