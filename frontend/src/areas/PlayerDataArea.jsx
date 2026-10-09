import ComparisonView from '../ComparisonView'
import ConfirmedPrioritiesPanel from '../ConfirmedPrioritiesView'
import ProgressView from '../ProgressView'
import ReportPanel from '../ReportPanel'
import SummaryView from '../SummaryView'
import { playerDataTabs } from '../dashboardModel'
import { Section } from './DashboardParts'

// Player Data: one player's results for the period, in tabs. Without self-assessment there is no Comparison tab,
// and nothing derived from self-ratings is shown.
export default function PlayerDataArea({ team, player, period, periods, matrix, comparison, selfAssessment, history, view, onViewChange, confirmDiscard, onMessage, onReportDirty }) {
  const selfAssessmentOn = Boolean(team.self_assessment_enabled)
  const tabs = playerDataTabs(selfAssessmentOn)
  const shown = tabs.some(([id]) => id === view) ? view : 'summary'
  const ids = { teamId: String(team.id), playerId: String(player.id), periodId: String(period.id) }
  return <Section className="context-panel" title={`${player.name} · ${period.label}`} description="Explore individual assessment results">
    <nav className="subtabs" aria-label="Player data views">{tabs.map(([id, label]) =>
      <button aria-current={shown === id ? 'page' : undefined} className={shown === id ? 'active' : ''} key={id} type="button" onClick={() => { if (id !== shown && confirmDiscard()) onViewChange(id) }}>{label}</button>)}
    </nav>
    {shown === 'summary' && <SummaryView matrix={matrix} coach={comparison?.coach} player={selfAssessment} selfAssessmentOn={selfAssessmentOn} />}
    {shown === 'comparison' && <ComparisonView matrix={matrix} coach={comparison?.coach} player={selfAssessment} />}
    {shown === 'progress' && <ProgressView matrix={matrix} history={history} />}
    {shown === 'priorities' && <ConfirmedPrioritiesPanel key={`${ids.teamId}-${ids.playerId}`} matrix={matrix} {...ids} periods={periods} />}
    {shown === 'report' && <ReportPanel key={`${ids.teamId}-${ids.playerId}-${ids.periodId}`} matrix={matrix} {...ids} readOnly={!player.active} onMessage={onMessage} onDirtyChange={onReportDirty} />}
  </Section>
}
