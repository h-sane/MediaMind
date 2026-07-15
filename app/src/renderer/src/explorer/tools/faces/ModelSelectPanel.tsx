import { useEffect, useState } from 'react'
import { useDownloadProvider, useProviders, useStartFaceScan } from '../../../api/hooks'
import { useJobsStore } from '../../../stores/jobs'
import { formatBytes } from '../../../lib/format'
import type { Provider } from '../../../api/client'

const RECOMMENDED_ID = 'opencv-yunet-sface'

const GUIDANCE_FOOTNOTE =
  "Accuracy figures are TAR@FAR=1e-6 from InsightFace's multi-racial benchmark " +
  '(github.com/deepinsight/insightface, model_zoo). Every available open model ' +
  'performs best on European/White faces; differences between groups are smaller ' +
  "in practice at MediaMind's clustering thresholds than at the benchmark's strict setting."

function LicenseBadge({ commercial_use }: { commercial_use: boolean }): React.JSX.Element {
  return commercial_use ? (
    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
      Permissive
    </span>
  ) : (
    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
      Non-commercial
    </span>
  )
}

function DownloadDialog({
  provider,
  onClose,
  onJobStarted
}: {
  provider: Provider
  onClose: () => void
  onJobStarted: (jobId: string) => void
}): React.JSX.Element {
  const [accepted, setAccepted] = useState(false)
  const download = useDownloadProvider()

  const handleDownload = () => {
    if (!accepted) return
    download.mutate(provider.id, {
      onSuccess: (job) => {
        onJobStarted(job.id)
        onClose()
      }
    })
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="text-base font-semibold">{provider.name}</h3>
        <p className="mt-1 text-sm text-zinc-500">{provider.description}</p>

        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">{provider.license.name}</p>
          <p className="mt-1 text-sm text-amber-800">{provider.license.summary}</p>
          <button
            className="mt-2 inline-block text-xs text-amber-700 underline hover:text-amber-900"
            onClick={() => window.open(provider.license.url, '_blank')}
          >
            Read full license →
          </button>
        </div>

        <label className="mt-4 flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={accepted}
            onChange={(e) => setAccepted(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-zinc-300"
          />
          <span className="text-sm text-zinc-700">I have read and accept the model license terms.</span>
        </label>

        {download.isError && <p className="mt-3 text-sm text-red-600">{download.error.message}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-zinc-200 px-4 py-2 text-sm text-zinc-600 hover:bg-zinc-50"
          >
            Cancel
          </button>
          <button
            onClick={handleDownload}
            disabled={!accepted || download.isPending}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:opacity-40"
          >
            {download.isPending ? 'Starting download…' : `Download (${formatBytes(provider.size_bytes)})`}
          </button>
        </div>
      </div>
    </div>
  )
}

function ModelCard({
  provider,
  selected,
  onSelect
}: {
  provider: Provider
  selected: boolean
  onSelect: () => void
}): React.JSX.Element {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [myJobId, setMyJobId] = useState<string | null>(null)
  const jobs = useJobsStore((s) => s.jobs)

  const myJob = myJobId ? jobs[myJobId] : null
  const isDownloading = !!myJob && (myJob.state === 'queued' || myJob.state === 'running')
  const downloadProgress =
    isDownloading && myJob && myJob.total > 0 ? Math.round((myJob.done / myJob.total) * 100) : null

  return (
    <>
      <div
        onClick={() => provider.installed && onSelect()}
        className={`rounded-2xl border p-5 shadow-sm transition ${
          provider.installed ? 'cursor-pointer' : ''
        } ${selected ? 'border-zinc-900 ring-1 ring-zinc-900' : 'border-zinc-200 bg-white hover:border-zinc-300'}`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div
              className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 ${
                selected ? 'border-zinc-900 bg-zinc-900' : 'border-zinc-300'
              }`}
            >
              {selected && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold">{provider.name}</h3>
                <LicenseBadge commercial_use={provider.license.commercial_use} />
                {provider.id === RECOMMENDED_ID && !provider.installed && (
                  <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                    Recommended
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-zinc-500">{provider.description}</p>
              <p className="mt-1 text-xs text-zinc-400">
                {provider.embedding_dim}-dim embeddings
                {provider.size_bytes > 0 ? ` · ${formatBytes(provider.size_bytes)} download` : ''}
              </p>
              {provider.guidance && (
                <div className="mt-3 rounded-lg bg-zinc-50 px-3 py-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-400">
                    Who it&apos;s best for
                  </p>
                  <p className="mt-0.5 text-xs leading-relaxed text-zinc-600">{provider.guidance}</p>
                </div>
              )}
            </div>
          </div>

          {provider.installed ? (
            <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Installed
            </span>
          ) : isDownloading ? (
            <div className="shrink-0 text-right">
              <p className="text-xs text-zinc-500">
                {myJob?.phase ?? 'downloading'}
                {downloadProgress !== null ? ` ${downloadProgress}%` : '…'}
              </p>
              {downloadProgress !== null && (
                <div className="mt-1 h-1.5 w-24 overflow-hidden rounded-full bg-zinc-200">
                  <div
                    className="h-full rounded-full bg-zinc-900 transition-all"
                    style={{ width: `${downloadProgress}%` }}
                  />
                </div>
              )}
            </div>
          ) : (
            <button
              onClick={(e) => {
                e.stopPropagation()
                setDialogOpen(true)
              }}
              className="shrink-0 rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-zinc-700"
            >
              Download
            </button>
          )}
        </div>
      </div>

      {dialogOpen && (
        <DownloadDialog provider={provider} onClose={() => setDialogOpen(false)} onJobStarted={(id) => setMyJobId(id)} />
      )}
    </>
  )
}

interface Props {
  libraryId: string
  defaultProviderId?: string
  onScanStarted: () => void
}

/** Model-selection gate shown before EVERY face scan (not just when no model
 * is installed yet) — a folder's demographic mix can differ, so the choice is
 * made fresh each time instead of silently reusing whichever model happened
 * to be installed first. */
export function ModelSelectPanel({ libraryId, defaultProviderId, onScanStarted }: Props): React.JSX.Element {
  const { data: providers, isLoading, isError } = useProviders()
  const startScan = useStartFaceScan(libraryId)
  const [selectedId, setSelectedId] = useState<string | null>(defaultProviderId ?? null)

  const sorted = providers
    ? [...providers].sort((a, b) => (a.id === RECOMMENDED_ID ? -1 : b.id === RECOMMENDED_ID ? 1 : 0))
    : []

  useEffect(() => {
    if (!providers || selectedId) return
    const preferred =
      providers.find((p) => p.id === defaultProviderId && p.installed) ??
      providers.find((p) => p.installed)
    if (preferred) setSelectedId(preferred.id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providers])

  const selectedProvider = providers?.find((p) => p.id === selectedId)
  const canScan = !!selectedProvider?.installed

  const handleScan = () => {
    if (!canScan) return
    startScan.mutate(selectedId ?? undefined, { onSuccess: onScanStarted })
  }

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto p-6 pb-28">
        <div className="mb-6">
          <h2 className="text-lg font-semibold tracking-tight">Choose a face-recognition model</h2>
          <p className="mt-1 text-sm text-zinc-500">
            Models run entirely on your device. Nothing leaves your machine. Pick the model that best
            fits this folder — you can choose a different one next time.
          </p>
        </div>

        {isLoading && <p className="text-sm text-zinc-400">Loading…</p>}
        {isError && <p className="text-sm text-red-600">Could not load models.</p>}

        {sorted.length > 0 && (
          <div className="space-y-3">
            {sorted.map((p) => (
              <ModelCard key={p.id} provider={p} selected={p.id === selectedId} onSelect={() => setSelectedId(p.id)} />
            ))}
          </div>
        )}

        {sorted.length > 0 && <p className="mt-4 text-xs text-zinc-400">{GUIDANCE_FOOTNOTE}</p>}
      </div>

      <div className="shrink-0 border-t border-zinc-200 bg-white px-6 py-4">
        <button
          onClick={handleScan}
          disabled={!canScan || startScan.isPending}
          className="w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {startScan.isPending
            ? 'Starting scan…'
            : selectedProvider
              ? `Scan this folder with ${selectedProvider.name}`
              : 'Select a model to scan with'}
        </button>
        {startScan.isError && (
          <p className="mt-2 text-center text-sm text-red-600">{(startScan.error as Error).message}</p>
        )}
      </div>
    </div>
  )
}
