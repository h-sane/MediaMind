import { useState } from 'react'
import {
  useDismissGlobalMoveSuggestion,
  useExecuteGlobalMove,
  useGlobalMoveSuggestions,
  useUndoableGlobalMove,
  useUndoGlobalMove
} from '../../../api/hooks'
import type { GlobalMoveSuggestionGroup, GlobalMoveSuggestionItem } from '../../../api/client'

/** Bulk review of files virtually tagged to a person with a primary
 * location set, not yet physically there. Nothing here has moved anything
 * yet — every button routes through `useExecuteGlobalMove`'s dry-run ->
 * real-execute pair (`core/global_people.py`'s `execute_move_plan`, which
 * reuses `core/safety.py`'s copy-then-delete/manifest/count-check
 * unchanged), and a real move always asks for confirmation first. */

function itemKey(libraryId: string, fileId: number): string {
  return `${libraryId}:${fileId}`
}

function ConfirmMoveDialog({
  count,
  destination,
  onConfirm,
  onCancel,
  isPending
}: {
  count: number
  destination: string
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}): React.JSX.Element {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl">
        <h3 className="mb-2 text-sm font-semibold">Move {count} files?</h3>
        <p className="mb-5 text-xs text-zinc-500">
          Files will be moved (not copied) into{' '}
          <code className="rounded bg-zinc-100 px-1 break-all">{destination}</code>, possibly across drives. This
          changes your original files on disk. You can undo this afterwards.
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

function SuggestionRow({
  item,
  selected,
  onToggle,
  onDismiss,
  dismissing
}: {
  item: GlobalMoveSuggestionItem
  selected: boolean
  onToggle: () => void
  onDismiss: () => void
  dismissing: boolean
}): React.JSX.Element {
  const filename = item.abs_path.split(/[\\/]/).pop() ?? item.abs_path
  return (
    <div className="flex items-center gap-3 rounded-xl border border-zinc-200 bg-white px-3 py-2">
      <input type="checkbox" checked={selected} onChange={onToggle} className="h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-zinc-800">{filename}</p>
        <p className="truncate text-xs text-zinc-400">{item.abs_path}</p>
      </div>
      <button
        onClick={onDismiss}
        disabled={dismissing}
        className="shrink-0 text-xs text-zinc-400 hover:text-red-600 disabled:opacity-50"
        title="Never suggest this file again"
      >
        Not this one
      </button>
    </div>
  )
}

function GroupSection({
  group,
  excluded,
  onToggleItem,
  onToggleAll
}: {
  group: GlobalMoveSuggestionGroup
  excluded: Set<string>
  onToggleItem: (key: string) => void
  onToggleAll: (group: GlobalMoveSuggestionGroup, select: boolean) => void
}): React.JSX.Element {
  const dismiss = useDismissGlobalMoveSuggestion()
  const execute = useExecuteGlobalMove()
  const [showConfirm, setShowConfirm] = useState(false)
  const [resultMessage, setResultMessage] = useState<string | null>(null)

  const selectedItems = group.items.filter((i) => !excluded.has(itemKey(i.library_id, i.file_id)))
  const allSelected = selectedItems.length === group.items.length && group.items.length > 0

  const handleConfirmMove = async () => {
    setShowConfirm(false)
    try {
      const dry = await execute.mutateAsync({
        items: selectedItems.map((i) => ({
          global_person_id: group.global_person_id,
          library_id: i.library_id,
          file_id: i.file_id
        })),
        dry_run: true
      })
      const real = await execute.mutateAsync({
        items: selectedItems.map((i) => ({
          global_person_id: group.global_person_id,
          library_id: i.library_id,
          file_id: i.file_id
        })),
        dry_run: false,
        expected_count: dry.planned,
        expected_plan_hash: dry.plan_hash
      })
      setResultMessage(
        real.ok
          ? `Moved ${real.handled} of ${real.planned} files.`
          : `Moved ${real.handled} of ${real.planned} — some failed, see the manifest at ${real.manifest_path}.`
      )
    } catch (e) {
      setResultMessage(e instanceof Error ? e.message : 'Move failed — refresh and try again.')
    }
  }

  return (
    <section className="space-y-2">
      {showConfirm && (
        <ConfirmMoveDialog
          count={selectedItems.length}
          destination={group.primary_location}
          onConfirm={handleConfirmMove}
          onCancel={() => setShowConfirm(false)}
          isPending={execute.isPending}
        />
      )}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-zinc-800">{group.global_person_name}</h3>
          <p className="text-xs text-zinc-500 break-all">→ {group.primary_location}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={() => onToggleAll(group, !allSelected)}
            className="text-xs text-zinc-500 hover:underline"
          >
            {allSelected ? 'Deselect all' : 'Select all'}
          </button>
          <button
            onClick={() => setShowConfirm(true)}
            disabled={selectedItems.length === 0 || execute.isPending}
            className="rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
          >
            Move {selectedItems.length} here
          </button>
        </div>
      </div>
      <div className="space-y-1.5">
        {group.items.map((item) => (
          <SuggestionRow
            key={itemKey(item.library_id, item.file_id)}
            item={item}
            selected={!excluded.has(itemKey(item.library_id, item.file_id))}
            onToggle={() => onToggleItem(itemKey(item.library_id, item.file_id))}
            onDismiss={() =>
              item.content_hash &&
              dismiss.mutate({ global_person_id: group.global_person_id, content_hash: item.content_hash })
            }
            dismissing={dismiss.isPending}
          />
        ))}
      </div>
      {resultMessage && <p className="text-xs text-zinc-600">{resultMessage}</p>}
    </section>
  )
}

function UndoLastMoveBar(): React.JSX.Element | null {
  const { data: info } = useUndoableGlobalMove()
  const undo = useUndoGlobalMove()
  const [message, setMessage] = useState<string | null>(null)

  if (!info?.available && !message) return null

  const handleUndo = async () => {
    setMessage(null)
    try {
      const report = await undo.mutateAsync()
      setMessage(
        report.ok
          ? `Moved ${report.handled} files back.`
          : `Moved ${report.handled} of ${report.planned} back — some failed, see ${report.manifest_path}.`
      )
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Undo failed.')
    }
  }

  return (
    <div className="mb-4 flex items-center justify-between rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5">
      <p className="text-xs text-zinc-600">
        {info?.available
          ? `Last move: ${info.file_count} file${info.file_count === 1 ? '' : 's'} can be moved back.`
          : (message ?? '')}
      </p>
      {info?.available && (
        <button
          onClick={handleUndo}
          disabled={undo.isPending}
          className="shrink-0 rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-white disabled:opacity-50"
        >
          {undo.isPending ? 'Undoing…' : 'Undo last move'}
        </button>
      )}
    </div>
  )
}

export function GlobalMoveSuggestionsPanel(): React.JSX.Element {
  const { data: groups, isPending, isError } = useGlobalMoveSuggestions()
  const [excluded, setExcluded] = useState<Set<string>>(new Set())

  const toggleItem = (key: string) => {
    setExcluded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const toggleAll = (group: GlobalMoveSuggestionGroup, select: boolean) => {
    setExcluded((prev) => {
      const next = new Set(prev)
      for (const item of group.items) {
        const key = itemKey(item.library_id, item.file_id)
        if (select) next.delete(key)
        else next.add(key)
      }
      return next
    })
  }

  return (
    <div className="h-full overflow-y-auto p-6 pb-24">
      <div className="mb-6">
        <h2 className="text-lg font-semibold tracking-tight">Suggestions</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Files tagged to a person with a primary location set, not yet physically there. Nothing moves until you
          confirm.
        </p>
      </div>

      <UndoLastMoveBar />

      {isPending && <p className="text-sm text-zinc-400">Checking every library…</p>}
      {isError && <p className="text-sm text-red-600">Could not load move suggestions.</p>}
      {!isPending && !isError && (!groups || groups.length === 0) && (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-16 text-center">
          <p className="text-sm text-zinc-500">
            No pending moves. Set a primary location for a person in the Global People tab to start seeing
            suggestions here.
          </p>
        </div>
      )}

      <div className="space-y-8">
        {groups?.map((group) => (
          <GroupSection
            key={group.global_person_id}
            group={group}
            excluded={excluded}
            onToggleItem={toggleItem}
            onToggleAll={toggleAll}
          />
        ))}
      </div>
    </div>
  )
}
