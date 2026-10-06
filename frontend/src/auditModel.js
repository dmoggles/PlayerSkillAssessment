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
    case 'age_group_changed': return d.to == null ? `${actor} cleared the age group` : `${actor} set the age group to U${d.to}${d.from == null ? '' : ` (was U${d.from})`}`
    case 'player_gender_changed': return `${actor} changed player wording from ${d.from} to ${d.to}`
    case 'report_shared': return d.replaced
      ? `${actor} created a new report link for ${d.player} (${d.period}), replacing the previous one`
      : `${actor} shared the report for ${d.player} (${d.period})`
    case 'report_share_revoked': return `${actor} revoked the report link for ${d.player} (${d.period})`
    default: return `${actor}: ${event.action}`
  }
}
