import { useState } from 'react'
import PrioritiesView from '../PrioritiesView'
import SquadPlans from '../SquadPlans'
import { priorityFollowUp } from '../followUpModel'
import { ArchivedNotice, Section } from './DashboardParts'

// Development: squad-wide plan generation, then the player's priorities, cycle and plan.
export default function DevelopmentArea({ teamId, player, period, periods, matrix, comparison, selfAssessment, history, onPrioritiesDirty, onRestorePlayer }) {
  // Bumped after a squad plan run, so the open player's plan reloads.
  const [squadRun, setSquadRun] = useState(0)
  const ids = { teamId: String(teamId), playerId: String(player.id), periodId: String(period.id) }
  return <Section className="context-panel" title={`${player.name} · ${period.label}`} description={player.active ? 'Review and confirm the three most important priorities' : 'Priorities (read-only)'}>
    {!player.active && <ArchivedNotice player={player} onRestore={onRestorePlayer} />}
    <SquadPlans teamId={ids.teamId} periodId={ids.periodId} onGenerated={() => setSquadRun(n => n + 1)} />
    <PrioritiesView key={`${ids.playerId}-${ids.periodId}-${squadRun}`} matrix={matrix} coach={comparison?.coach} player={selfAssessment} {...ids}
      followUp={priorityFollowUp(periods, history, ids.periodId, comparison?.coach)} onDirtyChange={onPrioritiesDirty} readOnly={!player.active} />
  </Section>
}
