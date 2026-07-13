import { useEffect, useMemo, useRef, useState } from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { ChevronDown } from 'lucide-react'
import { usePersons, useProviders, useStartFaceScan } from '../../../api/hooks'
import { selectJobForLibrary, useJobsStore } from '../../../stores/jobs'
import { OrganizePanel } from './OrganizePanel'
import { PeoplePanel } from './PeoplePanel'
import { PersonDetailPanel } from './PersonDetailPanel'
import { ProviderGate } from './ProviderGate'

interface Props {
  libraryId: string
  folderPath: string
}

type FacesSub = { name: 'people' } | { name: 'person'; personId: number } | { name: 'organize' }

/**
 * Faces tool root — gates on having a model installed (`ProviderGate`), then
 * hosts the People → Person detail → Organize sub-navigation locally (this
 * replaces the orphaned `stores/app.ts` view machine the original screens
 * used). Round-1 scope omits Pending/Multi-person review (see handoff).
 */
export function FacesToolPanel({ libraryId, folderPath: _folderPath }: Props): React.JSX.Element {
  const { data: providers, isLoading: providersLoading } = useProviders()
  const installed = useMemo(() => (providers ?? []).filter((p) => p.installed), [providers])

  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null)
  useEffect(() => {
    if (installed.length > 0 && (!selectedProviderId || !installed.some((p) => p.id === selectedProviderId))) {
      setSelectedProviderId(installed[0].id)
    }
  }, [installed, selectedProviderId])

  const [sub, setSub] = useState<FacesSub>({ name: 'people' })

  const jobs = useJobsStore((s) => s.jobs)
  const activeJob = selectJobForLibrary(jobs, libraryId, 'faces')
  const { data: personsData, isLoading: personsLoading } = usePersons(libraryId)
  const startFaceScan = useStartFaceScan(libraryId)
  const autoScanTriggered = useRef<string | null>(null)

  // First-run: once a model is installed, opening the tool on a folder with
  // no prior face scan starts one automatically — same convention as dedupe.
  useEffect(() => {
    if (installed.length === 0 || personsLoading || activeJob) return
    // personsData only resolves once a scan has already run (404 until then,
    // per usePersons's retry:false) — its presence at all means "don't rescan".
    if (personsData) return
    if (autoScanTriggered.current === libraryId) return
    autoScanTriggered.current = libraryId
    startFaceScan.mutate(selectedProviderId ?? undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [libraryId, installed.length, personsLoading, personsData, activeJob])

  if (providersLoading) {
    return <div className="p-6 text-sm text-zinc-400">Loading…</div>
  }

  if (installed.length === 0) {
    return <ProviderGate />
  }

  const selectedProvider = installed.find((p) => p.id === selectedProviderId) ?? installed[0]

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-end border-b border-zinc-100 px-6 py-2">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-100">
              Model: {selectedProvider?.name ?? '—'}
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={4}
              className="z-50 w-56 rounded-lg border border-zinc-200 bg-white py-1 text-sm shadow-lg"
            >
              {installed.map((p) => (
                <DropdownMenu.Item
                  key={p.id}
                  onSelect={() => setSelectedProviderId(p.id)}
                  className={`cursor-pointer px-3 py-1.5 outline-none hover:bg-zinc-100 ${
                    p.id === selectedProvider?.id ? 'font-medium text-zinc-900' : 'text-zinc-600'
                  }`}
                >
                  {p.name}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>

      <div className="min-h-0 flex-1">
        {sub.name === 'people' && (
          <PeoplePanel
            libraryId={libraryId}
            onOpenPerson={(personId) => setSub({ name: 'person', personId })}
            onOrganize={() => setSub({ name: 'organize' })}
          />
        )}
        {sub.name === 'person' && (
          <PersonDetailPanel libraryId={libraryId} personId={sub.personId} onBack={() => setSub({ name: 'people' })} />
        )}
        {sub.name === 'organize' && <OrganizePanel libraryId={libraryId} onBack={() => setSub({ name: 'people' })} />}
      </div>
    </div>
  )
}
