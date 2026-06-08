// Dev: '/api' via the Vite proxy. Prod: set VITE_API_URL to the backend's URL.
const BASE = import.meta.env.VITE_API_URL ?? '/api'

// Exported so EventSource/SSE callers resolve the same base (relative proxy in
// dev, absolute backend URL in prod) instead of hardcoding '/api'.
export const API_BASE = BASE

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...init?.headers },
      ...init,
    })
  } catch (networkError) {
    throw new Error(`Network error — is the server running? (${networkError})`)
  }

  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      message = body.detail ?? body.error ?? body.message ?? message
    } catch { /* body not JSON — keep status message */ }
    throw new Error(message)
  }

  return res.json()
}

export interface Job {
  id: number
  base_id: string
  table_id: string
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed'
  pause_reason?: string | null
  created_at: string
  total_records?: number
  total_batches?: number
}

export interface Batch {
  id: number
  job_id: number
  batch_number: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  processed: number
  hits: number
  misses: number
  failed: number
  total: number
  started_at?: string
  completed_at?: string
}

export interface WarmPathRun {
  id: number
  base_id: string
  table_id: string
  enrichment_job_id?: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  triggered_by: 'auto' | 'manual'
  contacts_loaded?: number
  targets_found?: number
  paths_found?: number
  error?: string
  created_at: string
  completed_at?: string
}

export interface EmbeddingRun {
  id: number
  base_id: string
  table_id: string
  enrichment_job_id?: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  triggered_by: 'auto' | 'manual'
  total_contacts?: number
  indexed?: number
  skipped?: number
  failed?: number
  error?: string
  created_at: string
  completed_at?: string
}

export interface AirtableField {
  id: string
  name: string
  type: string
  options?: { choices?: { name: string; color?: string }[] }
}

export interface CanonicalField {
  key: string
  label: string
  group: string
  description?: string
}

export interface Mapping {
  id: number
  name: string
  base_id: string
  table_id: string
  mappings: Record<string, {
    airtable_name: string
    airtable_type: string
    choices: string[]
    canonical_key: string
  }>
  created_at: string
}

export interface Campaign {
  id: number
  base_id: string
  table_id: string
  goal: string
  status: 'draft' | 'segmenting' | 'ready' | 'in_progress' | 'completed' | 'failed'
  error?: string
  tier_1_count: number
  tier_2_count: number
  tier_3_count: number
  tier_1_insight?: string
  tier_2_insight?: string
  tier_3_insight?: string
  sent_count: number
  skipped_count: number
  emails_sent: number
  created_at: string
  updated_at: string
  completed_at?: string
}

export interface ContactSnapshot {
  name: string
  title?: string
  company?: string
  email?: string
  signals?: {
    giving?: string
    wealth?: string
    capacity?: string
    trajectory?: string
    engagement?: string
    topics?: string
    personality?: string
  }
}

export interface ScoreBreakdown {
  warm_path: number
  post_signal: number
  rag: number
  capacity: number
  trajectory: number
  engagement: number
}

export interface CampaignContact {
  id: number
  campaign_id: number
  airtable_record_id: string
  tier: 'tier_1' | 'tier_2' | 'tier_3'
  tier_override?: string
  composite_score: number
  score_breakdown: ScoreBreakdown
  ai_reasoning?: string
  warm_path_data?: { connector?: string; score: number; evidence?: string }
  contact_snapshot: ContactSnapshot
  status: 'pending' | 'sent' | 'skipped' | 'later'
  queue_position: number
  sent_at?: string
  sent_draft?: string
}

export interface SequenceReply {
  name: string
  email: string
  title: string
  company: string
  replied_at: string | null
}

export interface SequenceBounce {
  name: string
  email: string
  title: string
  company: string
  bounced_at: string | null
  reason: string | null
  smtp_status: string | null
  hard: boolean | null
  detected_at: string | null
}

export interface Suppression {
  id: number
  email: string
  reason: 'hard_bounce' | 'soft_bounce' | 'mx_invalid' | 'sync_rejected' | 'unsubscribed' | 'manual'
  first_seen_at: string
  last_seen_at: string
  retry_after: string | null
  last_smtp_status: string | null
  last_reason_text: string | null
}

export interface BounceAuditEvent {
  id: number
  email: string
  source: 'sequence' | 'batch' | 'mx_preflight' | 'sync_error' | 'dsn'
  sequence_enrollment_id: number | null
  batch_job_id: number | null
  hard: boolean
  reason: string | null
  smtp_status: string | null
  source_message_id: string | null
  dsn_message_id: string | null
  detected_at: string
}

export interface SequenceStats {
  total: number
  active: number
  replied: number
  completed: number
  stopped: number
  bounced: number
  clicks?: number             // total clicks recorded against any enrollment in this sequence
  unique_clickers?: number    // distinct contacts who clicked at least once
  by_step: Record<string, number>
  next_by_step?: Record<string, string>  // step → ISO timestamp of next scheduled send
  next_send_at?: string | null            // earliest upcoming send across all steps (ISO)
}

export interface SequenceClick {
  name: string
  email: string
  title: string
  company: string
  click_count: number
  last_link_url: string | null
  last_click_at: string | null
}

export interface SequenceStep {
  id: number
  sequence_id: number
  step_number: number
  delay_days: number
  template_id: number
}

export interface Sequence {
  id: number
  campaign_id: number
  tier: 'tier_1' | 'tier_2' | 'tier_3'
  name: string
  status: 'draft' | 'active' | 'paused' | 'completed'
  sender_emails: string[]
  test_recipient?: string | null
  created_at: string
  updated_at: string
  campaign_goal?: string
  steps?: SequenceStep[]
  step_previews?: { step_number: number; delay_days: number; subject: string }[]
  stats?: SequenceStats
}

export interface JobFailureRecord {
  record_id: string
  linkedin_url: string
  reason: string
  error: string
}

export interface JobFailures {
  total_failed: number
  reasons: { reason: string; count: number }[]
  records: JobFailureRecord[]
  truncated: boolean
}

export interface SegmentationEvent {
  type: 'started' | 'progress' | 'complete' | 'error' | 'warning' | 'done'
  message: string
  step?: string
  count?: number
  indexed?: number
  total?: number
  goal_weights?: Record<string, number>
  tier_counts?: { tier_1: number; tier_2: number; tier_3: number }
}

export interface DedupRun {
  id: number
  base_id: string
  table_id: string
  enrichment_job_id?: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  triggered_by: 'auto' | 'manual'
  records_checked?: number
  groups_found?: number
  records_deleted?: number
  error?: string
  created_at: string
  completed_at?: string
}

export interface SignalScan {
  total: number
  signals: Record<string, { count: number; pct: number }>
  contact_fields: Record<string, { count: number; pct: number }>
}

export interface CampaignTemplate {
  id: number
  campaign_id: number
  tier: 'tier_1' | 'tier_2' | 'tier_3'
  subject: string
  body: string
  variables: string[]
  tier_summary?: string
  status: 'draft' | 'approved'
  created_at: string
  updated_at: string
}

export interface PreviewContact {
  contact_id: number
  contact_name: string
  rendered_subject: string
  rendered_body: string
  resolved_vars: string[]
  fallback_vars: string[]
  omitted_vars: string[]
}

export interface PreflightResult {
  record_count: number
  batch_count: number
  batch_size: number
}

export interface GmailStatus {
  connected: boolean
  email: string | null
}

export interface GmailAccount {
  email: string
  connected: true
}

export interface EmailProviderInfo {
  provider: 'gmail' | 'smtp' | 'resend'
  from_email: string | null
  requires_account: boolean
}

export type BatchSendScope = 'unsent' | 'everyone'

export interface BatchEmailJob extends Omit<BatchSendJob, never> {
  campaign_goal: string
}

// Single-job lookup returns the same fields PLUS the campaign's pitch_page
// info (joined server-side so the detail page doesn't need a second call).
export interface BatchJobDetail extends BatchEmailJob {
  pitch_page_url: string | null
  pitch_page_label: string | null
  // Estimated time when Gmail's rolling 24h send quota will free up enough
  // to resume — computed from the earliest send in the past 24h + 24h.
  // null when there's no recent send activity to estimate from.
  quota_resets_at: string | null
}

export interface BatchJobBounce {
  name: string
  email: string
  title: string
  company: string
  reason: string | null
  smtp_status: string | null
  hard: boolean | null
  detected_at: string | null
}

export interface BatchSendJob {
  id: number
  campaign_id: number
  template_id: number
  tier: 'tier_1' | 'tier_2' | 'tier_3'
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled'
  total: number
  sent: number
  failed: number
  scope: BatchSendScope
  error?: string
  // Set to 'rate_limited' when the runner auto-paused because all senders hit
  // Gmail's daily quota. Null on manual pause. Drives the "Gmail hit its
  // quota" banner so it only shows when that's actually what happened.
  pause_reason?: string | null
  retry_after?: string
  started_at?: string
  completed_at?: string
  created_at: string
}

export interface TierStat {
  pending: number
  sent: number
  skipped: number
  later: number
  total: number
  template_status: 'draft' | 'approved' | null
  latest_job: Pick<BatchSendJob, 'id' | 'status' | 'total' | 'sent' | 'failed' | 'scope' | 'created_at'> | null
}

export interface ScopeCounts {
  unsent: number
  everyone: number
}

export const api = {
  health:     () =>
    request<{ status: string }>('/health'),

  listJobs:   (base_id: string, table_id: string) =>
    request<{ jobs: Job[] }>(`/jobs?base_id=${base_id}&table_id=${table_id}`)
      .then(r => r.jobs),

  deleteJob:  (id: number) =>
    request<{ success: boolean }>(`/jobs/${id}`, { method: 'DELETE' }),

  runJob:     (id: number) =>
    request<{ success: boolean; status: string }>(`/jobs/${id}/run`, { method: 'POST' }),

  rerunJob:   (id: number) =>
    request<{ success: boolean }>(`/jobs/${id}/rerun`, { method: 'POST' }),

  pauseJob:   (id: number) =>
    request<{ success: boolean; status: string }>(`/jobs/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'paused' }),
    }),

  resumeJob:  (id: number) =>
    request<{ success: boolean; status: string }>(`/jobs/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'running' }),
    }),

  getBatches: (jobId: number) =>
    request<{ batches: Batch[] }>(`/jobs/${jobId}/batches`)
      .then(r => r.batches),

  getJobFailures: (jobId: number) =>
    request<JobFailures>(`/jobs/${jobId}/failures`),

  // --- Cadence / sequences ---
  createSequence: (
    campaignId: number,
    body: { tier: string; name?: string; steps: { delay_days: number; template_id: number }[]; sender_emails?: string[]; test_recipient?: string },
  ) =>
    request<{ id: number }>(`/campaigns/${campaignId}/sequences`, { method: 'POST', body: JSON.stringify(body) }),

  launchSequence: (sequenceId: number, scope: 'everyone' | 'unsent' = 'everyone') =>
    request<{ enrolled: number }>(`/sequences/${sequenceId}/launch?scope=${scope}`, { method: 'POST' }),

  pauseSequence: (sequenceId: number) =>
    request<{ success: boolean }>(`/sequences/${sequenceId}/pause`, { method: 'POST' }),

  resumeSequence: (sequenceId: number) =>
    request<{ success: boolean }>(`/sequences/${sequenceId}/resume`, { method: 'POST' }),

  deleteSequence: (sequenceId: number) =>
    request<{ success: boolean }>(`/sequences/${sequenceId}`, { method: 'DELETE' }),

  getSequenceReplies: (sequenceId: number) =>
    request<{ replies: SequenceReply[] }>(`/sequences/${sequenceId}/replies`).then(r => r.replies),

  getSequenceBounces: (sequenceId: number) =>
    request<{ bounces: SequenceBounce[] }>(`/sequences/${sequenceId}/bounces`).then(r => r.bounces),

  getSequenceClicks: (sequenceId: number) =>
    request<{ clicks: SequenceClick[] }>(`/sequences/${sequenceId}/clicks`).then(r => r.clicks),

  listSuppressions: (opts: { limit?: number; offset?: number; search?: string } = {}) => {
    const qs = new URLSearchParams()
    if (opts.limit !== undefined)  qs.set('limit',  String(opts.limit))
    if (opts.offset !== undefined) qs.set('offset', String(opts.offset))
    if (opts.search)               qs.set('search', opts.search)
    const q = qs.toString()
    return request<{ suppressions: Suppression[]; active_count: number }>(
      `/suppressions${q ? `?${q}` : ''}`,
    )
  },

  getSuppressionBounces: (email: string, limit = 50) =>
    request<{ bounces: BounceAuditEvent[] }>(
      `/suppressions/${encodeURIComponent(email)}/bounces?limit=${limit}`,
    ).then(r => r.bounces),

  unsuppress: (email: string) =>
    request<{ removed: boolean }>(`/suppressions/unsuppress`, {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  getSequence: (sequenceId: number) =>
    request<Sequence>(`/sequences/${sequenceId}`),

  listSequences: (campaignId: number, tier?: string) =>
    request<{ sequences: Sequence[] }>(`/campaigns/${campaignId}/sequences${tier ? `?tier=${tier}` : ''}`)
      .then(r => r.sequences),

  listAllSequences: (baseId: string, tableId: string) =>
    request<{ sequences: Sequence[] }>(`/sequences?base_id=${encodeURIComponent(baseId)}&table_id=${encodeURIComponent(tableId)}`)
      .then(r => r.sequences),

  warmPathStatus: (job_id: number) =>
    request<{ run: WarmPathRun | null }>(`/warm-path/status?job_id=${job_id}`)
      .then(r => r.run),

  warmPathStatusGlobal: (base_id: string, table_id: string) =>
    request<{ run: WarmPathRun | null }>(`/warm-path/status?base_id=${base_id}&table_id=${table_id}`)
      .then(r => r.run),

  warmPathRun: (job_id: number) =>
    request<{ success: boolean; message: string }>('/warm-path/run', {
      method: 'POST',
      body: JSON.stringify({ job_id }),
    }),

  warmPathRunGlobal: (base_id: string, table_id: string) =>
    request<{ success: boolean; message: string }>('/warm-path/run', {
      method: 'POST',
      body: JSON.stringify({ base_id, table_id }),
    }),

  embeddingStatus: (job_id: number) =>
    request<{ run: EmbeddingRun | null }>(`/embedding/status?job_id=${job_id}`)
      .then(r => r.run),

  embeddingStatusGlobal: (base_id: string, table_id: string) =>
    request<{ run: EmbeddingRun | null }>(`/embedding/status?base_id=${base_id}&table_id=${table_id}`)
      .then(r => r.run),

  embeddingRun: (job_id: number) =>
    request<{ success: boolean; message: string }>('/embedding/run', {
      method: 'POST',
      body: JSON.stringify({ job_id }),
    }),

  embeddingRunGlobal: (base_id: string, table_id: string) =>
    request<{ success: boolean; message: string }>('/embedding/run', {
      method: 'POST',
      body: JSON.stringify({ base_id, table_id }),
    }),

  dedupStatus: (job_id: number) =>
    request<{ run: DedupRun | null }>(`/dedup/status?job_id=${job_id}`)
      .then(r => r.run),

  dedupRun: (job_id: number) =>
    request<{ success: boolean; message: string }>('/dedup/run', {
      method: 'POST',
      body: JSON.stringify({ job_id }),
    }),

  // --- Mappings ---
  listMappings: (base_id: string, table_id: string) =>
    request<{ mappings: Mapping[] }>(`/mappings?base_id=${base_id}&table_id=${table_id}`)
      .then(r => r.mappings),

  saveMapping: (base_id: string, table_id: string, name: string, mappings: Mapping['mappings']) =>
    request<{ success: boolean; id: number }>('/mappings', {
      method: 'POST',
      body: JSON.stringify({ base_id, table_id, name, mappings }),
    }),

  updateMapping: (id: number, base_id: string, table_id: string, name: string, mappings: Mapping['mappings']) =>
    request<{ success: boolean; id: number }>(`/mappings/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ base_id, table_id, name, mappings }),
    }),

  deleteMapping: (id: number) =>
    request<{ success: boolean }>(`/mappings/${id}`, { method: 'DELETE' }),

  // --- Schema ---
  getSchema: (base_id: string, table_id: string) =>
    request<{ fields: AirtableField[]; table_name: string }>(`/schema?base_id=${base_id}&table_id=${table_id}`),

  getCanonicalSchema: () =>
    request<{ fields: CanonicalField[] }>('/canonical-schema'),

  // --- Campaigns ---
  listCampaigns: (base_id: string, table_id: string) =>
    request<{ campaigns: Campaign[] }>(`/campaigns?base_id=${base_id}&table_id=${table_id}`)
      .then(r => r.campaigns),

  createCampaign: (
    base_id: string,
    table_id: string,
    goal: string,
    mapping_id?: number,
    extras?: { pitch_page_url?: string; pitch_page_label?: string },
  ) =>
    // Returns the full campaign in the response so callers don't need a
    // follow-up GET.
    request<{ campaign_id: number; status: string; campaign: Campaign | null }>('/campaigns', {
      method: 'POST',
      body: JSON.stringify({ base_id, table_id, goal, mapping_id, ...(extras ?? {}) }),
    }),

  getCampaign: (id: number) =>
    request<{ campaign: Campaign }>(`/campaigns/${id}`).then(r => r.campaign),

  deleteCampaign: (id: number) =>
    request<{ success: boolean }>(`/campaigns/${id}`, { method: 'DELETE' }),

  getCampaignQueue: (id: number, tier: string, offset = 0, limit = 50) =>
    request<{ contacts: CampaignContact[]; count: number; has_more: boolean }>(
      `/campaigns/${id}/queue/${tier}?offset=${offset}&limit=${limit}`
    ),

  getCampaignStats: (id: number) =>
    request<{ stats: Record<string, TierStat> }>(`/campaigns/${id}/stats`)
      .then(r => r.stats),

  sendContact: (campaignId: number, contactId: number, sent_draft: string) =>
    request<{ success: boolean }>(`/campaigns/${campaignId}/contacts/${contactId}/send`, {
      method: 'POST',
      body: JSON.stringify({ sent_draft }),
    }),

  skipContact: (campaignId: number, contactId: number) =>
    request<{ success: boolean }>(`/campaigns/${campaignId}/contacts/${contactId}/skip`, {
      method: 'POST',
    }),

  parkContact: (campaignId: number, contactId: number) =>
    request<{ success: boolean }>(`/campaigns/${campaignId}/contacts/${contactId}/later`, {
      method: 'POST',
    }),

  // --- Signal Scan ---
  getSignalScan: (campaignId: number, tier: string) =>
    request<{ scan: SignalScan }>(`/campaigns/${campaignId}/templates/${tier}/signal-scan`)
      .then(r => r.scan),

  // --- Campaign Templates ---
  getCampaignTemplate: (campaignId: number, tier: string) =>
    request<{ template: CampaignTemplate }>(`/campaigns/${campaignId}/templates/${tier}`)
      .then(r => r.template),

  getTemplateById: (campaignId: number, templateId: number) =>
    request<{ template: CampaignTemplate }>(`/campaigns/${campaignId}/templates/by-id/${templateId}`)
      .then(r => r.template),

  createNewTemplate: (campaignId: number, tier: string) =>
    request<{ template: CampaignTemplate }>(`/campaigns/${campaignId}/templates/${tier}/new`, {
      method: 'POST',
    }).then(r => r.template),

  saveCampaignTemplate: (campaignId: number, tier: string, data: {
    subject?: string; body?: string; variables?: string[]; tier_summary?: string; template_id?: number
  }) =>
    request<{ template: CampaignTemplate }>(`/campaigns/${campaignId}/templates/${tier}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }).then(r => r.template),

  approveCampaignTemplate: (campaignId: number, tier: string) =>
    request<{ success: boolean }>(`/campaigns/${campaignId}/templates/${tier}/approve`, {
      method: 'POST',
    }),

  generateCampaignTemplate: (campaignId: number, tier: string) =>
    request<{ template: CampaignTemplate }>(`/campaigns/${campaignId}/templates/${tier}/generate`, {
      method: 'POST',
    }).then(r => r.template),

  previewCampaignTemplate: (campaignId: number, tier: string, subject: string, body: string, count = 5) =>
    request<{ previews: PreviewContact[] }>(`/campaigns/${campaignId}/templates/${tier}/preview`, {
      method: 'POST',
      body: JSON.stringify({ subject, body, count }),
    }).then(r => r.previews),

  parseTemplateFile: (campaignId: number, file: File): Promise<{ text: string; detected_vars: string[] }> => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/campaigns/${campaignId}/parse-file`, { method: 'POST', body: form })
      .then(r => r.ok ? r.json() : r.json().then((e: any) => Promise.reject(new Error(e.error ?? 'Upload failed'))))
  },

  uploadCampaignDeck: (campaignId: number, file: File): Promise<{ id: number; filename: string; chars: number }> => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/campaigns/${campaignId}/deck`, { method: 'POST', body: form })
      .then(r => r.ok ? r.json() : r.json().then((e: any) => Promise.reject(new Error(e.error ?? 'Deck upload failed'))))
  },

  // --- Gmail OAuth ---
  getGmailStatus: () =>
    request<GmailStatus>('/auth/gmail/status'),

  listGmailAccounts: () =>
    request<{ accounts: GmailAccount[] }>('/auth/gmail/accounts').then(r => r.accounts),

  getEmailProvider: () =>
    request<EmailProviderInfo>('/auth/email/provider'),

  disconnectGmail: (email?: string) =>
    request<{ success: boolean }>(`/auth/gmail${email ? `?email=${encodeURIComponent(email)}` : ''}`, { method: 'DELETE' }),

  // --- Batch Send ---
  getScopeCounts: (campaignId: number, tier: string) =>
    request<ScopeCounts>(`/campaigns/${campaignId}/templates/${tier}/scope-counts`),

  createBatchSendJob: (
    campaignId: number,
    tier: string,
    scope: BatchSendScope,
    templateId?: number,
    senderEmails?: string[],
    testRecipient?: string,
  ) =>
    request<{ job: BatchSendJob }>(`/campaigns/${campaignId}/templates/${tier}/send`, {
      method: 'POST',
      body: JSON.stringify({
        scope,
        template_id: templateId,
        sender_emails: senderEmails ?? [],
        test_recipient: testRecipient ?? null,
      }),
    }).then(r => r.job),

  listBatchSendJobs: (campaignId: number, tier?: string) =>
    request<{ jobs: BatchSendJob[] }>(
      `/campaigns/${campaignId}/batch-jobs${tier ? `?tier=${tier}` : ''}`
    ).then(r => r.jobs),

  cancelBatchSendJob: (campaignId: number, jobId: number) =>
    request<{ success: boolean }>(`/campaigns/${campaignId}/batch-jobs/${jobId}/cancel`, { method: 'POST' }),

  pauseBatchSendJob: (campaignId: number, jobId: number) =>
    request<{ success: boolean }>(`/campaigns/${campaignId}/batch-jobs/${jobId}/pause`, { method: 'POST' }),

  resumeBatchSendJob: (campaignId: number, jobId: number) =>
    request<{ success: boolean }>(`/campaigns/${campaignId}/batch-jobs/${jobId}/resume`, { method: 'POST' }),

  deleteBatchSendJob: (campaignId: number, jobId: number) =>
    request<{ success: boolean }>(`/campaigns/${campaignId}/batch-jobs/${jobId}`, { method: 'DELETE' }),

  getBatchJob: (jobId: number) =>
    request<BatchJobDetail>(`/batch-jobs/${jobId}`),

  getBatchJobBounces: (jobId: number) =>
    request<{ bounces: BatchJobBounce[] }>(`/batch-jobs/${jobId}/bounces`).then(r => r.bounces),

  getBatchJobClicks: (jobId: number) =>
    // Same row shape as a sequence click — name/email/title/company + counts.
    request<{ clicks: SequenceClick[] }>(`/batch-jobs/${jobId}/clicks`).then(r => r.clicks),

  listAllBatchEmailJobs: (base_id: string, table_id: string) =>
    request<{ jobs: BatchEmailJob[] }>(`/batch-jobs?base_id=${base_id}&table_id=${table_id}`)
      .then(r => r.jobs),

  // --- Job creation ---
  jobPreflight: (base_id: string, table_id: string, view_id: string, batch_size: number) =>
    request<PreflightResult>('/jobs/preflight', {
      method: 'POST',
      body: JSON.stringify({ base_id, table_id, view_id, batch_size }),
    }),

  createJob: (base_id: string, table_id: string, view_id: string, linkedin_url_field: string, name_field: string, batch_size: number) =>
    request<{ job_id: number; record_count: number; total_batches: number }>('/jobs/create', {
      method: 'POST',
      body: JSON.stringify({ base_id, table_id, view_id, linkedin_url_field, name_field, batch_size }),
    }),
}
