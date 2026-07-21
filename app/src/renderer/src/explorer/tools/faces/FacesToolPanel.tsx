import { useEffect, useRef, useState } from 'react'
import { usePersons } from '../../../api/hooks'
import { personPath, useExplorerStore } from '../../../stores/explorer'
import { selectJobForLibrary, useJobsStore } from '../../../stores/jobs'
import { ModelSelectPanel } from './ModelSelectPanel'
import { MultiPersonPanel } from './MultiPersonPanel'
import { OrganizePanel } from './OrganizePanel'
import { PendingReviewPanel } from './PendingReviewPanel'
import { PeoplePanel } from './PeoplePanel'
import { PrepPanel } from './PrepPanel'

interface Props {
  libraryId: string
  folderPath: string
}

type FacesSub =
  | { name: 'prep' }
  | { name: 'setup' }
  | { name: 'people' }
  | { name: 'organize' }
  | { name: 'pending' }
  | { name: 'multi-person' }

/**
 * Faces tool root — hosts the Prep (loose vs. pre-sorted check) → Setup
 * (model choice) → People → Person detail → Organize sub-navigation locally
 * (this replaces the orphaned `stores/app.ts` view machine the original
 * screens used).
 *
 * A scan never starts on its own: opening the tool on a folder with no prior
 * face scan lands on Prep first, then Setup, and Rescan always returns
 * straight to Setup rather than re-running silently — a folder's demographic
 * mix can call for a different model each time, so the choice isn't a
 * one-time global default.
 */
export function FacesToolPanel({ libraryId, folderPath }: Props): React.JSX.Element {
  const [sub, setSub] = useState<FacesSub>({ name: 'prep' })
  const navigate = useExplorerStore((s) => s.navigate)

  const jobs = useJobsStore((s) => s.jobs)
  const activeJob = selectJobForLibrary(jobs, libraryId, 'faces')
  const { data: personsData, isLoading: personsLoading } = usePersons(libraryId)
  const initialSubResolved = useRef<string | null>(null)

  // Phase 4: opening a person navigates the Explorer to a virtual "place" that
  // shows their real files in the main content grid (all view modes, the
  // progressive viewer, no files moved) rather than a bespoke side panel.
  const openPerson = (personId: number) => {
    const p = personsData?.persons.find((pp) => pp.id === personId)
    navigate(personPath(folderPath, personId, p?.name ?? p?.auto_label ?? `Person ${personId}`))
  }

  // Land on People if a scan already exists for this folder, Setup otherwise
  // — once per folder, so explicit navigation (Rescan, back) isn't overridden.
  useEffect(() => {
    if (personsLoading || initialSubResolved.current === libraryId) return
    initialSubResolved.current = libraryId
    setSub(personsData ? { name: 'people' } : { name: 'prep' })
  }, [libraryId, personsLoading, personsData])

  const goToSetup = () => setSub({ name: 'setup' })
  const goToPeople = () => setSub({ name: 'people' })

  return (
    <div className="flex h-full flex-col">
      {sub.name !== 'setup' && sub.name !== 'prep' && (
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
        {sub.name === 'prep' && <PrepPanel libraryId={libraryId} onReady={goToSetup} />}
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
            onOpenPerson={openPerson}
            onOrganize={() => setSub({ name: 'organize' })}
            onReviewPending={() => setSub({ name: 'pending' })}
            onReviewMultiPerson={() => setSub({ name: 'multi-person' })}
          />
        )}
        {sub.name === 'organize' && <OrganizePanel libraryId={libraryId} onBack={goToPeople} />}
        {sub.name === 'pending' && <PendingReviewPanel libraryId={libraryId} onBack={goToPeople} />}
        {sub.name === 'multi-person' && <MultiPersonPanel libraryId={libraryId} onBack={goToPeople} />}
      </div>
    </div>
  )
}
