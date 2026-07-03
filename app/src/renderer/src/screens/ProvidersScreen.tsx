import { useState } from 'react'
import { useAppStore } from '../stores/app'
import { useJobsStore } from '../stores/jobs'
import { useProviders, useDownloadProvider } from '../api/hooks'
import { formatBytes } from '../lib/format'
import type { Provider } from '../api/client'

interface Props {
  libraryId: string
}

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
  onJobStarted,
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
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative z-10 w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="text-base font-semibold">{provider.name}</h3>
        <p className="mt-1 text-sm text-zinc-500">{provider.description}</p>

        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
            {provider.license.name}
          </p>
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
          <span className="text-sm text-zinc-700">
            I have read and accept the model license terms.
          </span>
        </label>

        {download.isError && (
          <p className="mt-3 text-sm text-red-600">{download.error.message}</p>
        )}

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
            {download.isPending
              ? 'Starting download…'
              : `Download (${formatBytes(provider.size_bytes)})`}
          </button>
        </div>
      </div>
    </div>
  )
}

function ProviderCard({ provider }: { provider: Provider }): React.JSX.Element {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [myJobId, setMyJobId] = useState<string | null>(null)
  const jobs = useJobsStore((s) => s.jobs)

  // Track the specific download job started by THIS card — prevents one card's
  // download from showing progress on all cards simultaneously.
  const myJob = myJobId ? jobs[myJobId] : null
  const isDownloading = !!myJob && (myJob.state === 'queued' || myJob.state === 'running')

  const downloadProgress =
    isDownloading && myJob && myJob.total > 0
      ? Math.round((myJob.done / myJob.total) * 100)
      : null

  return (
    <>
      <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold">{provider.name}</h3>
              <LicenseBadge commercial_use={provider.license.commercial_use} />
            </div>
            <p className="mt-1 text-xs text-zinc-500">{provider.description}</p>
            <p className="mt-1 text-xs text-zinc-400">
              {provider.embedding_dim}-dim embeddings{provider.size_bytes > 0 ? ` · ${formatBytes(provider.size_bytes)} download` : ''}
            </p>
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
              onClick={() => setDialogOpen(true)}
              className="shrink-0 rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-zinc-700"
            >
              Download
            </button>
          )}
        </div>
      </div>

      {dialogOpen && (
        <DownloadDialog
          provider={provider}
          onClose={() => setDialogOpen(false)}
          onJobStarted={(id) => setMyJobId(id)}
        />
      )}
    </>
  )
}

export function ProvidersScreen({ libraryId: _libraryId }: Props): React.JSX.Element {
  const back = useAppStore((s) => s.back)
  const { data: providers, isLoading, isError } = useProviders()

  return (
    <section className="mx-auto w-full max-w-3xl px-8 py-12">
      <button
        onClick={back}
        className="mb-6 flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600"
      >
        ← Back
      </button>

      <div className="mb-8">
        <h2 className="text-lg font-semibold tracking-tight">Face recognition models</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Models run entirely on your device. Nothing leaves your machine.
        </p>
      </div>

      {isLoading && <p className="text-sm text-zinc-400">Loading…</p>}
      {isError && <p className="text-sm text-red-600">Could not load providers.</p>}

      {providers && (
        <div className="space-y-3">
          {providers.map((p) => (
            <ProviderCard key={p.id} provider={p} />
          ))}
        </div>
      )}
    </section>
  )
}
