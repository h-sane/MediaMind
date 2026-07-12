import { NavButtons } from './NavButtons'
import { AddressBar } from './AddressBar'
import { SearchBox } from './SearchBox'

interface Props {
  onRefresh: () => void
  refreshing: boolean
}

export function TopChrome({ onRefresh, refreshing }: Props): React.JSX.Element {
  return (
    <div className="flex items-center gap-2 border-b border-zinc-200 px-3 py-2">
      <NavButtons onRefresh={onRefresh} refreshing={refreshing} />
      <AddressBar />
      <SearchBox />
    </div>
  )
}
