// Human-readable sentences for team audit events.
export function auditText(event) {
  const actor = event.actor_email
  const target = event.target_email
  const d = event.details ?? {}
  switch (event.action) {
    case 'team_created': return `${actor} created the team`
    case 'team_renamed': return `${actor} renamed the team from ${d.from} to ${d.to}`
    case 'self_assessment_enabled': return `${actor} turned on player self-assessment`
    case 'self_assessment_disabled': return `${actor} turned off player self-assessment`
    case 'invite_sent': return `${actor} invited ${target}`
    case 'invite_accepted': return `${actor} joined the team`
    case 'role_changed': return d.to === 'owner' ? `${actor} made ${target} an owner` : `${actor} changed ${target} to a coach`
    case 'member_removed': return `${actor} removed ${target}`
    case 'member_left': return `${actor} left the team`
    case 'period_deleted': return `${actor} deleted the period ${d.label}`
    case 'team_deleted': return `${actor} deleted the team`
    case 'matrix_published': return `${actor} published skill matrix version ${d.version}${d.applied_to ? ` (also used for ${d.applied_to})` : ''}`
    case 'playing_group_changed': return d.to == null ? `${actor} cleared ${d.player}'s playing group (${d.period})` : `${actor} set ${d.player}'s playing group to U${d.to} (${d.period})${d.from == null ? '' : `, was U${d.from}`}`
    case 'age_group_changed': return d.to == null ? `${actor} cleared the age group` : `${actor} set the age group to U${d.to}${d.from == null ? '' : ` (was U${d.from})`}`
    case 'player_gender_changed': return `${actor} changed player wording from ${d.from} to ${d.to}`
    case 'report_shared': return d.replaced
      ? `${actor} created a new report link for ${d.player} (${d.period}), replacing the previous one`
      : `${actor} shared the report for ${d.player} (${d.period})`
    case 'plan_saved': return `${actor} ${d.replaced ? 'regenerated' : 'generated'} the development plan for ${d.player} (${d.period})`
    case 'report_share_extended': return `${actor} extended the report link for ${d.player} (${d.period}) by ${d.weeks} week${d.weeks === 1 ? '' : 's'}`
    case 'plan_shared': return d.replaced
      ? `${actor} created a new plan link for ${d.player} (${d.period}), replacing the previous one`
      : `${actor} shared a development plan for ${d.player} (${d.period})`
    case 'plan_share_revoked': return `${actor} revoked the plan link for ${d.player} (${d.period})`
    case 'report_share_revoked': return `${actor} revoked the report link for ${d.player} (${d.period})`
    default: return `${actor}: ${event.action}`
  }
}
