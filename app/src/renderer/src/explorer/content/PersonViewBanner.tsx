import { useState } from 'react'
import {
  usePersons,
  useSetPrimaryFolder,
  useOrganizePreview,
  useOrganizeExecuteJob
} from '../../api/hooks'
import { useJobsStore } from '../../stores/jobs'

interface Props {
  libraryId: string
  personId: number
}

/** Same confirm-dialog shape as `OrganizePanel`'s `ConfirmOrganizeDialog`, but
 * scoped to one person's files moving into their primary folder — always a
 * move (never copy), so the warning is unconditional rather than mode-driven. */
function ConfirmMoveDialog({
  planned,
  destination,
  onConfirm,
  onCancel,
  isPending
}: {
  planned: number
  destination: string
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}): React.JSX.Element {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl">
        <h3 className="mb-2 text-sm font-semibold">Move {planned} files?</h3>
        <p className="mb-5 text-xs text-zinc-500">
          Files will be moved (not copied) into <code className="rounded bg-zinc-100 px-1">{destination}</code>.
          This changes your original files on disk. You can undo this afterwards.
        </p>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg border border-zinc-200 px-4 py-2 text-sm text-zinc-600 hover:bg-zinc-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
          >
            {isPending ? 'Moving…' : 'Move'}
          </button>
        </div>
      </div>
    </div>
  )
}

/** Banner shown above the content grid when browsing a person's virtual view
 * (`mediamind:person:...`, see `parsePersonView`). Lets the user pin a real
 * "primary folder" for this person and move their prominent files there —
 * the actual file-op flow mirrors `OrganizePanel`'s preview → confirm →
 * background job pattern, just pre-scoped to one person. */
export function PersonViewBanner({ libraryId, personId }: Props): React.JSX.Element | null {
  const { data: personsData } = usePersons(libraryId)
  const person = personsData?.persons.find((p) => p.id === personId)
  const setPrimaryFolder = useSetPrimaryFolder(libraryId)

  const primaryFolder = person?.primary_folder_path ?? null
  const { data: preview } = useOrganizePreview(libraryId, 'prominent', personId)
  const executeJob = useOrganizeExecuteJob(libraryId)

  const [showConfirm, setShowConfirm] = useState(false)
  const [pendingJobId, setPendingJobId] = useState<string | null>(null)
  const jobs = useJobsStore((s) => s.jobs)
  const pendingJob = pendingJobId ? jobs[pendingJobId] : undefined

  if (!person) return null

  const handlePickFolder = async () => {
    const path = await window.mediamind.pickFolder()
    if (path) setPrimaryFolder.mutate({ personId, path })
  }

  const handleClear = () => setPrimaryFolder.mutate({ personId, path: null })

  const planned = preview?.planned ?? 0

  const handleConfirmMove = () => {
    executeJob.mutate(
      {
        mode: 'move',
        groupScope: 'prominent',
        personId,
        expectedPlanned: preview?.planned,
        expectedPlanHash: preview?.plan_hash
      },
      {
        onSuccess: (snap) => {
          setPendingJobId(snap.id)
          setShowConfirm(false)
        }
      }
    )
  }

  return (
    <div className="border-b border-zinc-200 bg-zinc-50 px-6 py-3">
      {showConfirm && primaryFolder && (
        <ConfirmMoveDialog
          planned={planned}
          destination={primaryFolder}
          onConfirm={handleConfirmMove}
          onCancel={() => setShowConfirm(false)}
          isPending={executeJob.isPending}
        />
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-zinc-600">
          {primaryFolder ? (
            <>
              Primary folder: <span className="font-medium text-zinc-800">{primaryFolder}</span>
            </>
          ) : (
            'No primary folder set.'
          )}
        </p>

        <div className="flex items-center gap-2">
          <button
            onClick={handlePickFolder}
            disabled={setPrimaryFolder.isPending}
            className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
          >
            {primaryFolder ? 'Change folder…' : 'Set primary folder…'}
          </button>
          {primaryFolder && (
            <button
              onClick={handleClear}
              disabled={setPrimaryFolder.isPending}
              className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs text-zinc-500 hover:bg-zinc-50 disabled:opacity-50"
            >
              Clear
            </button>
          )}
          {primaryFolder && (
            <button
              onClick={() => setShowConfirm(true)}
              disabled={planned === 0 || executeJob.isPending}
              title={planned === 0 ? 'No files to move' : undefined}
              className="rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
            >
              {planned === 0 ? 'No files to move' : `Move ${planned} files here`}
            </button>
          )}
        </div>
      </div>

      {executeJob.isError && (
        <p className="mt-2 text-xs text-red-600">{executeJob.error.message}</p>
      )}
      {pendingJob?.state === 'succeeded' && (
        <p className="mt-2 text-xs text-emerald-700">Move complete.</p>
      )}
      {pendingJob?.state === 'failed' && (
        <p className="mt-2 text-xs text-red-600">Move failed — see the job log.</p>
      )}
    </div>
  )
}
