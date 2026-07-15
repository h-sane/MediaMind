import { useEffect, useRef, useState } from 'react'
import { usePersons } from '../../../api/hooks'
import { selectJobForLibrary, useJobsStore } from '../../../stores/jobs'
import { ModelSelectPanel } from './ModelSelectPanel'
import { OrganizePanel } from './OrganizePanel'
import { PeoplePanel } from './PeoplePanel'
import { PersonDetailPanel } from './PersonDetailPanel'

interface Props {
  libraryId: string
  folderPath: string
}

type FacesSub =
  | { name: 'setup' }
  | { name: 'people' }
  | { name: 'person'; personId: number }
  | { name: 'organize' }

/**
 * Faces tool root — hosts the Setup (model choice) → People → Person detail
 * → Organize sub-navigation locally (this replaces the orphaned
 * `stores/app.ts` view machine the original screens used). Round-1 scope
 * omits Pending/Multi-person review (see handoff).
 *
 * A scan never starts on its own: opening the tool on a folder with no prior
 * face scan lands on Setup, and Rescan always returns to Setup rather than
 * re-running silently — a folder's demographic mix can call for a different
 * model each time, so the choice isn't a one-time global default.
 */
export function FacesToolPanel({ libraryId, folderPath: _folderPath }: Props): React.JSX.Element {
  const [sub, setSub] = useState<FacesSub>({ name: 'setup' })

  const jobs = useJobsStore((s) => s.jobs)
  const activeJob = selectJobForLibrary(jobs, libraryId, 'faces')
  const { data: personsData, isLoading: personsLoading } = usePersons(libraryId)
  const initialSubResolved = useRef<string | null>(null)

  // Land on People if a scan already exists for this folder, Setup otherwise
  // — once per folder, so explicit navigation (Rescan, back) isn't overridden.
  useEffect(() => {
    if (personsLoading || initialSubResolved.current === libraryId) return
    initialSubResolved.current = libraryId
    setSub(personsData ? { name: 'people' } : { name: 'setup' })
  }, [libraryId, personsLoading, personsData])

  const goToSetup = () => setSub({ name: 'setup' })
  const goToPeople = () => setSub({ name: 'people' })

  return (
    <div className="flex h-full flex-col">
      {sub.name !== 'setup' && (
        <div className="flex items-center justify-between border-b border-zinc-100 px-6 py-2">
          <span className="text-xs text-zinc-500">Model: {personsData?.provider_id ?? '—'}</span>
          <button
            onClick={goToSetup}
            disabled={!!activeJob}
            className="rounded-md px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-100 disabled:opacity-40"
          >
            Rescan…
          </button>
        </div>
      )}

      <div className="min-h-0 flex-1">
        {sub.name === 'setup' && (
          <ModelSelectPanel
            libraryId={libraryId}
            defaultProviderId={personsData?.provider_id}
            onScanStarted={goToPeople}
          />
        )}
        {sub.name === 'people' && (
          <PeoplePanel
            libraryId={libraryId}
            onOpenPerson={(personId) => setSub({ name: 'person', personId })}
            onOrganize={() => setSub({ name: 'organize' })}
          />
        )}
        {sub.name === 'person' && (
          <PersonDetailPanel libraryId={libraryId} personId={sub.personId} onBack={goToPeople} />
        )}
        {sub.name === 'organize' && <OrganizePanel libraryId={libraryId} onBack={goToPeople} />}
      </div>
    </div>
  )
}
