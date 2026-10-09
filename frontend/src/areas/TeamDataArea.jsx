import HeatmapView from '../HeatmapView'
import TeamInsights from '../TeamInsights'
import { TEAM_DATA_TABS, groupCounts } from '../dashboardModel'
import { Section } from './DashboardParts'

// Team Data: the squad for the period. A squad with two or more playing groups is shown one group at a time by
// default, since ratings are judged against each player's own group.
export default function TeamDataArea({ team, period, matrix, players, groups, heatmap, view, onViewChange, position, onPositionChange, groupChoice, onGroupChoice, onMessage }) {
  const present = groupCounts(players, groups)
  // groupChoice: null follows the default (the largest group), 'all' shows everyone. Fewer than two groups: no filter,
  // or players without a group would drop out.
  const chosen = present.length < 2 || groupChoice === 'all' ? null : present.some(g => g.age === groupChoice) ? groupChoice : present[0].age
  return <Section className="context-panel" title={`${team.name} · ${period.label}`} description="Compare skills across the squad">
    {present.length > 1 && <label className="field insights-filter team-group-filter">Playing group
      <select value={chosen ?? 'all'} onChange={e => onGroupChoice(e.target.value === 'all' ? 'all' : Number(e.target.value))}>
        {present.map(g => <option key={g.age} value={g.age}>U{g.age} ({g.players} {g.players === 1 ? 'player' : 'players'})</option>)}
        <option value="all">All groups (mixed age groups)</option>
      </select>
      <small>{chosen ? 'Ratings are judged against each player\'s own group, so groups are shown one at a time.' : 'Ratings from different groups are judged against different cohorts; compare with care.'}</small>
    </label>}
    <nav className="subtabs" aria-label="Team data views">{TEAM_DATA_TABS.map(([id, label]) =>
      <button aria-current={view === id ? 'page' : undefined} className={view === id ? 'active' : ''} key={id} type="button" onClick={() => onViewChange(id)}>{label}</button>)}
    </nav>
    {view === 'heatmap'
      ? <HeatmapView matrix={matrix} assessments={chosen ? heatmap.filter(a => groups[a.player_id] === chosen) : heatmap} />
      : <TeamInsights key={`${team.id}-${period.id}`} teamId={String(team.id)} periodId={String(period.id)} view={view} position={position} group={chosen} onPositionChange={onPositionChange} onMessage={onMessage} />}
  </Section>
}
