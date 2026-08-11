import { PageContainer } from '../../shared/layout/PageContainer'
import { EmptyState } from '../../shared/ui/EmptyState'
import { PageHeader } from '../../shared/ui/PageHeader'

export function SystemQualityPage() {
  return <PageContainer><PageHeader eyebrow="Jälgi" title="Süsteem ja kvaliteet" description="Selle vaate mõõdikud ja töövood lisanduvad järgmises arendusetapis." /><EmptyState title="Veel seadistamisel">Praegu ei koguta ega kuvata selles vaates süsteemi- või kvaliteedimõõdikuid.</EmptyState></PageContainer>
}
