import { useCallback, useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowRight, ChevronDown, Loader2, Network, Plus, RefreshCw, Save, Trash2, X, Zap } from 'lucide-react'
import { api, type AirtableField, type CanonicalField, type Mapping } from '@/shared/api/client'
import { Button } from '@/shared/components/ui/button'
import { Card } from '@/shared/components/ui/card'
import { MaskedInput } from '@/shared/components/ui/masked-id'
import { useJobConfig } from '@/shared/hooks/useJobConfig'
import { toast } from '@/shared/lib/toast'
import { cn } from '@/shared/lib/utils'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/shared/components/ui/sheet'

/* ─── helpers ──────────────────────────────────────────────── */

function autoMatch(fieldName: string, canonicalFields: CanonicalField[]): string {
  const norm = (s: string) => s.toLowerCase().replace(/[\s_\-]/g, '')
  const n = norm(fieldName)
  const match = canonicalFields.find(cf => {
    const cl = norm(cf.label)
    const ck = norm(cf.key)
    return cl === n || ck === n || cl.includes(n) || n.includes(cl)
  })
  return match?.key ?? ''
}

/* ─── MappingRow ────────────────────────────────────────────── */

interface MappingRowProps {
  field: AirtableField
  value: string
  canonicalOptions: React.ReactNode
  onChange: (fieldId: string, canonicalKey: string) => void
}

function MappingRow({ field, value, canonicalOptions, onChange }: MappingRowProps) {
  const mapped = Boolean(value)

  return (
    <div className="grid grid-cols-[1fr_20px_1fr] items-center gap-3 py-2 border-b border-border/20 last:border-0">
      <span className={cn(
        'font-mono text-sm truncate transition-colors',
        mapped ? 'text-foreground' : 'text-muted-foreground/50'
      )}>
        {field.name}
      </span>

      <ArrowRight size={12} className={cn('transition-colors shrink-0', mapped ? 'text-muted-foreground/40' : 'text-border')} />

      <div className="relative">
        <select
          value={value}
          onChange={e => onChange(field.id, e.target.value)}
          className={cn(
            'w-full appearance-none bg-transparent border-b pb-0.5 pr-5 text-sm font-mono',
            'focus:outline-none transition-colors',
            mapped
              ? 'border-primary/40 text-foreground'
              : 'border-border/40 text-muted-foreground/40'
          )}
        >
          {canonicalOptions}
        </select>
        <ChevronDown size={11} className="absolute right-0 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground/40" />
      </div>
    </div>
  )
}

/* ─── MappingSheet ───────────────────────────────────────────── */

interface MappingSheetProps {
  open: boolean
  onOpenChange: (o: boolean) => void
  baseId: string
  tableId: string
  existingMapping?: Mapping
  onSaved: () => void
}

function MappingSheet({ open, onOpenChange, baseId, tableId, existingMapping, onSaved }: MappingSheetProps) {
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const [airtableFields, setAirtableFields] = useState<AirtableField[]>([])
  const [canonicalFields, setCanonicalFields] = useState<CanonicalField[]>([])
  const [selections, setSelections] = useState<Record<string, string>>({})
  const [showAll, setShowAll]       = useState(true)
  const [name, setName]             = useState('')
  const [saving, setSaving]         = useState(false)
  const [saveError, setSaveError]   = useState<string | null>(null)
  const nameRef = useRef<HTMLInputElement>(null)

  const isEditing = Boolean(existingMapping)

  useEffect(() => {
    if (!open || !baseId || !tableId) return
    setLoading(true)
    setError(null)
    setSaveError(null)

    // Prefill name from existing mapping
    setName(existingMapping?.name ?? '')

    Promise.all([
      api.getSchema(baseId, tableId),
      api.getCanonicalSchema(),
    ]).then(([tableData, canonical]) => {
      setAirtableFields(tableData.fields)
      setCanonicalFields(canonical.fields)

      const initial: Record<string, string> = {}
      tableData.fields.forEach(f => {
        // Prefill from existing mapping if editing, otherwise auto-match
        if (existingMapping?.mappings[f.id]) {
          initial[f.id] = existingMapping.mappings[f.id].canonical_key
        } else {
          initial[f.id] = autoMatch(f.name, canonical.fields)
        }
      })
      setSelections(initial)
      setShowAll(tableData.fields.length <= 15 || isEditing)
    }).catch(e => {
      setError(String(e))
    }).finally(() => setLoading(false))
  }, [open, baseId, tableId, existingMapping, isEditing])

  const handleChange = useCallback((fieldId: string, key: string) => {
    setSelections(prev => ({ ...prev, [fieldId]: key }))
  }, [])

  const handleAutoMatch = () => {
    const next: Record<string, string> = {}
    airtableFields.forEach(f => { next[f.id] = autoMatch(f.name, canonicalFields) })
    setSelections(next)
  }

  const handleClear = () => {
    const next: Record<string, string> = {}
    airtableFields.forEach(f => { next[f.id] = '' })
    setSelections(next)
  }

  const handleSave = async () => {
    setSaveError(null)
    if (!name.trim()) {
      setSaveError('Enter a name for this mapping')
      nameRef.current?.focus()
      return
    }
    const mappings: Mapping['mappings'] = {}
    airtableFields.forEach(f => {
      const key = selections[f.id]
      if (key) {
        mappings[f.id] = {
          airtable_name: f.name,
          airtable_type: f.type,
          choices: f.options?.choices?.map(c => c.name) ?? [],
          canonical_key: key,
        }
      }
    })
    if (Object.keys(mappings).length === 0) {
      setSaveError('Map at least one field before saving')
      return
    }
    setSaving(true)
    try {
      if (isEditing && existingMapping) {
        await api.updateMapping(existingMapping.id, baseId, tableId, name.trim(), mappings)
        toast.success(`Mapping "${name.trim()}" updated`)
      } else {
        await api.saveMapping(baseId, tableId, name.trim(), mappings)
        toast.success(`Mapping "${name.trim()}" saved`)
      }
      onSaved()
      onOpenChange(false)
    } catch (e) {
      const msg = String(e)
      setSaveError(msg)
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }

  const canonicalOptions = (() => {
    if (canonicalFields.length === 0) return null
    const groups = [...new Set(canonicalFields.map(f => f.group))]
    return (
      <>
        <option value="">— skip —</option>
        {groups.map(g => (
          <optgroup key={g} label={g.toUpperCase()}>
            {canonicalFields.filter(f => f.group === g).map(f => (
              <option key={f.key} value={f.key} title={f.description}>{f.label}</option>
            ))}
          </optgroup>
        ))}
      </>
    )
  })()

  const mappedCount   = Object.values(selections).filter(Boolean).length
  const visibleFields = showAll ? airtableFields : airtableFields.filter(f => selections[f.id])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-2xl flex flex-col p-0 overflow-hidden">
        <SheetHeader className="px-5 pt-5 pb-4 border-b border-border shrink-0">
          <SheetTitle className="font-mono text-base tracking-tight">
            {isEditing ? 'Edit Mapping' : 'New Mapping'}
          </SheetTitle>
          {baseId && tableId && (
            <p className="text-xs text-muted-foreground font-mono">{tableId}</p>
          )}
        </SheetHeader>

        {loading && (
          <div className="flex-1 flex items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 size={16} className="animate-spin" /> Loading schema…
          </div>
        )}

        {error && (
          <div className="flex-1 flex items-center justify-center p-6">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {!loading && !error && airtableFields.length > 0 && (
          <>
            <div className="flex items-center gap-2 px-5 py-3 border-b border-border shrink-0">
              <span className="text-xs text-muted-foreground">
                {mappedCount} / {airtableFields.length} mapped
              </span>
              <div className="ml-auto flex items-center gap-2">
                <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={showAll}
                    onChange={e => setShowAll(e.target.checked)}
                    className="accent-primary"
                  />
                  Show all
                </label>
                <Button variant="ghost" size="sm" onClick={handleAutoMatch} className="h-7 px-2 text-xs gap-1">
                  <Zap size={12} /> Auto
                </Button>
                <Button variant="ghost" size="sm" onClick={handleClear} className="h-7 px-2 text-xs gap-1">
                  <X size={12} /> Clear
                </Button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-5">
              <AnimatePresence initial={false}>
                {visibleFields.map(f => (
                  <motion.div
                    key={f.id}
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.12 }}
                    className="overflow-hidden"
                  >
                    <MappingRow
                      field={f}
                      value={selections[f.id] ?? ''}
                      canonicalOptions={canonicalOptions}
                      onChange={handleChange}
                    />
                  </motion.div>
                ))}
              </AnimatePresence>
              {visibleFields.length === 0 && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No mapped fields — click Auto or toggle "Show all"
                </p>
              )}
            </div>

            <div className="shrink-0 px-5 py-4 border-t border-border space-y-3">
              {saveError && <p className="text-xs text-red-400">{saveError}</p>}
              <div className="flex items-center gap-2">
                <input
                  ref={nameRef}
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSave()}
                  placeholder="Mapping name…"
                  maxLength={60}
                  className="flex-1 bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring font-mono placeholder:text-muted-foreground"
                />
                <Button onClick={handleSave} disabled={saving} size="sm" className="shrink-0">
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                  {saving ? 'Saving…' : isEditing ? 'Update' : 'Save'}
                </Button>
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}

/* ─── MappingCard ────────────────────────────────────────────── */

interface MappingCardProps {
  mapping: Mapping
  onEdit: (m: Mapping) => void
  onDelete: (id: number) => void
}

function MappingCard({ mapping, onEdit, onDelete }: MappingCardProps) {
  const fieldCount = Object.keys(mapping.mappings).length

  return (
    <motion.div variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }}>
      <Card
        className="cursor-pointer hover:-translate-y-0.5 transition-transform duration-200"
        onClick={() => onEdit(mapping)}
      >
        <div className="pt-5 pb-4 px-5">
          {/* Top row: icon + delete */}
          <div className="flex items-start justify-between mb-4">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <Network size={16} />
            </div>
            <button
              onClick={e => { e.stopPropagation(); onDelete(mapping.id) }}
              className="p-1 rounded hover:bg-red-500/10 hover:text-red-400 text-muted-foreground/30 transition-colors"
            >
              <Trash2 size={13} />
            </button>
          </div>

          {/* Stat */}
          <p className="font-mono text-[10px] text-muted-foreground tracking-widest uppercase mb-1">Fields mapped</p>
          <p className="text-3xl font-bold tabular-nums text-primary">{fieldCount}</p>

          {/* Footer */}
          <div className="mt-4 pt-3 border-t border-border/40 flex items-end justify-between gap-2">
            <p className="font-mono text-sm font-medium text-foreground truncate leading-tight">{mapping.name}</p>
            <p className="font-mono text-[10px] text-muted-foreground/50 shrink-0 tabular-nums">
              {new Date(mapping.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>
      </Card>
    </motion.div>
  )
}

/* ─── Mappings page ──────────────────────────────────────────── */

export function Mappings() {
  const { config, updateConfig, isConfigured } = useJobConfig()
  const [draftBase,  setDraftBase]  = useState(config.baseId)
  const [draftTable, setDraftTable] = useState(config.tableId)

  const [mappings,       setMappings]       = useState<Mapping[]>([])
  const [loading,        setLoading]        = useState(false)
  const [error,          setError]          = useState<string | null>(null)
  const [sheetOpen,      setSheetOpen]      = useState(false)
  const [editingMapping, setEditingMapping] = useState<Mapping | undefined>(undefined)

  const loadMappings = useCallback(async (baseId: string, tableId: string) => {
    setLoading(true)
    setError(null)
    try {
      const list = await api.listMappings(baseId, tableId)
      setMappings(list)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isConfigured) void loadMappings(config.baseId, config.tableId)
  }, [config.baseId, config.tableId, isConfigured, loadMappings])

  const saveConfig = () => {
    updateConfig({ baseId: draftBase.trim(), tableId: draftTable.trim() })
  }

  const openNew = () => {
    setEditingMapping(undefined)
    setSheetOpen(true)
  }

  const openEdit = (m: Mapping) => {
    setEditingMapping(m)
    setSheetOpen(true)
  }

  const handleSheetClose = (open: boolean) => {
    setSheetOpen(open)
    if (!open) setEditingMapping(undefined)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.deleteMapping(id)
      setMappings(prev => prev.filter(m => m.id !== id))
      toast.success('Mapping deleted')
    } catch (e) {
      toast.error(String(e))
    }
  }

  return (
    <div className="flex flex-col h-full">

      {/* ── Sticky config bar ── */}
      <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border px-6 py-4">
        <div className="flex items-end gap-3">
          <div className="w-56 space-y-1.5">
            <label className="text-sm text-muted-foreground font-medium">Base ID</label>
            <MaskedInput
              value={draftBase}
              onChange={e => setDraftBase(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && saveConfig()}
              placeholder="appXXXXXXXX"
            />
          </div>
          <div className="w-56 space-y-1.5">
            <label className="text-sm text-muted-foreground font-medium">Table ID</label>
            <MaskedInput
              value={draftTable}
              onChange={e => setDraftTable(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && saveConfig()}
              placeholder="tblXXXXXXXX"
            />
          </div>
          <div className="flex items-center gap-2 pb-0.5">
            <Button size="sm" onClick={saveConfig} disabled={!draftBase.trim() || !draftTable.trim()}>
              <Save size={14} /> Load
            </Button>
            {isConfigured && (
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => void loadMappings(config.baseId, config.tableId)}
                disabled={loading}
              >
                <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              </Button>
            )}
          </div>
          <div className="ml-auto pb-0.5">
            <Button size="sm" onClick={openNew} disabled={!isConfigured}>
              <Plus size={14} /> New Mapping
            </Button>
          </div>
        </div>
      </div>

      {/* ── Content ── */}
      <div className="flex-1 overflow-y-auto px-6 py-5">

        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 size={16} className="animate-spin" /> Loading…
          </div>
        )}

        {error && <p className="text-sm text-red-400">{error}</p>}

        {!loading && !error && isConfigured && mappings.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <p className="text-sm text-muted-foreground">No mappings saved for this table.</p>
            <Button size="sm" variant="outline" onClick={openNew}>
              <Plus size={14} /> Create your first mapping
            </Button>
          </div>
        )}

        {!isConfigured && !loading && (
          <p className="py-20 text-center text-sm text-muted-foreground">
            Enter a Base ID and Table ID above to load mappings.
          </p>
        )}

        <motion.div
          className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 max-w-4xl"
          initial="hidden"
          animate="show"
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.06 } } }}
        >
          {mappings.map(m => (
            <MappingCard key={m.id} mapping={m} onEdit={openEdit} onDelete={handleDelete} />
          ))}
        </motion.div>

      </div>

      <MappingSheet
        open={sheetOpen}
        onOpenChange={handleSheetClose}
        baseId={config.baseId}
        tableId={config.tableId}
        existingMapping={editingMapping}
        onSaved={() => void loadMappings(config.baseId, config.tableId)}
      />
    </div>
  )
}
