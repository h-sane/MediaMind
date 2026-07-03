import { useState } from 'react'
import { useAppStore } from '../stores/app'
import { useMultiPersonFiles, useSetRouteChoices } from '../api/hooks'
import { FaceThumbnail } from '../components/FaceThumbnail'
import type { MultiPersonFile, PersonOption } from '../api/client'

interface Props {
  libraryId: string
}

function FileCard({
  file,
  libraryId,
  pendingChoice,
  onChoose,
}: {
  file: MultiPersonFile
  libraryId: string
  pendingChoice: number | null | undefined
  onChoose: (fileId: number, personId: number | null) => void
}): React.JSX.Element {
  // pendingChoice: undefined = not changed yet (show current_choice), null = clear, number = pick
  const effectiveChoice = pendingChoice !== undefined ? pendingChoice : file.current_choice
  const filename = file.path.split('/').pop() ?? file.path

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
      <p className="mb-1 truncate text-sm font-medium" title={file.path}>
        {filename}
      </p>
      <p className="mb-4 truncate text-xs text-zinc-400">{file.path}</p>

      <div className="flex flex-wrap gap-3">
        {file.persons.map((person: PersonOption) => {
          const isSelected = effectiveChoice === person.person_id
          return (
            <button
              key={person.person_id}
              onClick={() =>
                onChoose(file.file_id, isSelected ? null : person.person_id)
              }
              className={`flex flex-col items-center gap-2 rounded-xl border-2 p-3 transition ${
                isSelected
                  ? 'border-zinc-900 bg-zinc-50 shadow-md'
                  : 'border-zinc-200 bg-white hover:border-zinc-300 hover:shadow-sm'
              }`}
              title={isSelected ? 'Click to clear selection' : `Assign to ${person.person_name}`}
            >
              <FaceThumbnail
                libraryId={libraryId}
                faceId={person.sample_face_id}
                size={64}
                className={`ring-2 ${isSelected ? 'ring-zinc-900' : 'ring-white'} ring-offset-1`}
              />
              <span className={`max-w-[80px] truncate text-xs font-medium ${isSelected ? '' : 'text-zinc-500'}`}>
                {person.person_name}
              </span>
              <span className="text-xs text-zinc-400">
                {person.face_count} {person.face_count === 1 ? 'face' : 'faces'}
              </span>
            </button>
          )
        })}
      </div>

      {effectiveChoice === null && file.current_choice !== null && (
        <p className="mt-3 text-xs text-amber-600">Choice cleared — organizer will auto-pick</p>
      )}
    </div>
  )
}

export function MultiPersonReview({ libraryId }: Props): React.JSX.Element {
  const back = useAppStore((s) => s.back)
  const { data: files, isLoading, isError } = useMultiPersonFiles(libraryId)
  const setChoices = useSetRouteChoices(libraryId)

  // Track unsaved changes: fileId -> personId | null (null = clear)
  const [pendingChanges, setPendingChanges] = useState<Record<number, number | null>>({})
  const [saved, setSaved] = useState(false)

  const handleChoose = (fileId: number, personId: number | null) => {
    setSaved(false)
    setPendingChanges((prev) => ({ ...prev, [fileId]: personId }))
  }

  const handleSave = () => {
    const choices = Object.entries(pendingChanges).map(([fileId, personId]) => ({
      file_id: Number(fileId),
      person_id: personId ?? 0,  // 0 signals "clear" to the backend
    }))
    if (choices.length === 0) return

    setChoices.mutate(choices, {
      onSuccess: () => {
        setPendingChanges({})
        setSaved(true)
      }
    })
  }

  const hasPendingChanges = Object.keys(pendingChanges).length > 0

  return (
    <section className="mx-auto w-full max-w-3xl px-8 py-12">
      <div className="mb-2 flex items-center gap-2">
        <button
          onClick={back}
          className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600"
        >
          ← Back
        </button>
      </div>

      <div className="mb-6 flex items-end justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Multi-person files</h2>
          <p className="mt-1 text-sm text-zinc-500">
            These files contain faces from more than one person. Pick which person each file
            belongs to before organizing.
          </p>
        </div>
        {hasPendingChanges && (
          <button
            onClick={handleSave}
            disabled={setChoices.isPending}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:opacity-50"
          >
            {setChoices.isPending ? 'Saving…' : `Save ${Object.keys(pendingChanges).length} choice${Object.keys(pendingChanges).length === 1 ? '' : 's'}`}
          </button>
        )}
      </div>

      {saved && !hasPendingChanges && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          Choices saved. The organizer will now route these files to the selected person's folder.
        </div>
      )}

      {setChoices.isError && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {setChoices.error.message}
        </div>
      )}

      {isLoading && <p className="text-sm text-zinc-400">Loading…</p>}

      {isError && (
        <p className="text-sm text-red-600">
          Could not load multi-person files. Run a face scan first.
        </p>
      )}

      {!isLoading && files && files.length === 0 && (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">No multi-person files found.</p>
          <p className="mt-1 text-xs text-zinc-400">
            All files with face detections contain only one person.
          </p>
        </div>
      )}

      {files && files.length > 0 && (
        <div className="space-y-4">
          {files.map((file: MultiPersonFile) => (
            <FileCard
              key={file.file_id}
              file={file}
              libraryId={libraryId}
              pendingChoice={pendingChanges[file.file_id]}
              onChoose={handleChoose}
            />
          ))}
        </div>
      )}

      {files && files.length > 0 && hasPendingChanges && (
        <div className="mt-6 flex justify-end">
          <button
            onClick={handleSave}
            disabled={setChoices.isPending}
            className="rounded-lg bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:opacity-50"
          >
            {setChoices.isPending ? 'Saving…' : `Save ${Object.keys(pendingChanges).length} choice${Object.keys(pendingChanges).length === 1 ? '' : 's'}`}
          </button>
        </div>
      )}
    </section>
  )
}
