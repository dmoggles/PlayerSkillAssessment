import axios from 'axios'

export const api = axios.create({ baseURL: '/api', withCredentials: true })
let csrfToken = ''

api.interceptors.request.use(config => {
  if (csrfToken) config.headers['x-csrf-token'] = csrfToken
  return config
})

const data = promise => promise.then(response => response.data)
const team = id => `/teams/${id}`

export function errorMessage(error, fallback = 'Request failed. Please try again.') {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail.map(item => {
      if (typeof item === 'string') return item
      if (!item || typeof item.msg !== 'string') return null
      const field = Array.isArray(item.loc) ? item.loc.filter(part => !['body', 'query', 'path'].includes(part)).join('.') : ''
      return field ? `${field}: ${item.msg}` : item.msg
    }).filter(Boolean)
    if (messages.length) return messages.join(' ')
  }
  if (detail && typeof detail.msg === 'string') return detail.msg
  if (detail && typeof detail.message === 'string') return Array.isArray(detail.problems) && detail.problems.length ? `${detail.message}: ${detail.problems.join('; ')}` : detail.message
  return fallback
}

export const restoreSession = () => data(api.get('/auth/me')).then(value => { csrfToken = value.csrf_token; return value })
export const register = (email, password, invite = null) => data(api.post('/auth/register', { email, password, invite }))
export const resendVerification = email => data(api.post('/auth/resend-verification', { email }))
export const verify = token => data(api.post('/auth/verify', { token }))
export const login = (email, password) => data(api.post('/auth/login', { email, password })).then(value => { csrfToken = value.csrf_token; return value })
export const logout = () => data(api.post('/auth/logout')).finally(() => { csrfToken = '' })
export const forgotPassword = email => data(api.post('/auth/forgot-password', { email }))
export const resetPassword = (token, password) => data(api.post('/auth/reset-password', { token, password }))
export const deleteAccount = password => data(api.post('/auth/delete-account', { password })).finally(() => { csrfToken = '' })
export const changePassword = (currentPassword, newPassword) => data(api.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword }))
export const acceptInvite = token => data(api.post('/invites/accept', { token }))
export const getInvite = token => data(api.get(`/invites/${encodeURIComponent(token)}`))
export const suggestVideo = (slug, suggestion) => data(api.post(`/drills/${encodeURIComponent(slug)}/video-suggestions`, suggestion))
export const reportDrillLink = (slug, report) => data(api.post(`/drills/${encodeURIComponent(slug)}/link-reports`, report))
export const getLinkReportQueue = (status = 'open') => data(api.get('/admin/link-reports', { params: { status } }))
export const handleLinkReport = (id, action) => data(api.post(`/admin/link-reports/${id}/${action}`))
export const getMyVideoSuggestions = () => data(api.get('/me/video-suggestions'))
export const getVideoSuggestionQueue = (status = 'pending') => data(api.get('/admin/video-suggestions', { params: { status } }))
export const approveVideoSuggestion = (id, approval) => data(api.post(`/admin/video-suggestions/${id}/approve`, approval))
export const rejectVideoSuggestion = (id, rejection) => data(api.post(`/admin/video-suggestions/${id}/reject`, rejection))
export const getDrillSubmissionQueue = (status = 'pending') => data(api.get('/admin/drill-submissions', { params: { status } }))
export const acceptDrillSubmission = (id, librarySlug) => data(api.post(`/admin/drill-submissions/${id}/accept`, { library_slug: librarySlug }))
export const declineDrillSubmission = (id, reason) => data(api.post(`/admin/drill-submissions/${id}/decline`, { reason }))
export const getDrillSubmissionRow = id => data(api.get(`/admin/drill-submissions/${id}/row`))
export const requestAccess = request => data(api.post('/access-requests', request))
export const getAccessRequests = (status = 'pending') => data(api.get('/admin/access-requests', { params: { status } }))
export const inviteFromAccessRequest = id => data(api.post(`/admin/access-requests/${id}/invite`))
export const declineAccessRequest = id => data(api.post(`/admin/access-requests/${id}/decline`))
export const getSiteInvites = () => data(api.get('/admin/invites'))
export const sendSiteInvite = email => data(api.post('/admin/invites', { email }))
export const cancelSiteInvite = id => data(api.delete(`/admin/invites/${id}`))

export const getServerVersion = () => data(api.get('/health')).then(value => value.version)
// With a team, the library plus that team's own drills.
export const getDrills = teamId => data(api.get('/drills', { params: teamId ? { team_id: teamId } : {} }))
export const createTeamDrill = (id, drill) => data(api.post(`${team(id)}/drills`, drill))
export const updateTeamDrill = (id, slug, drill) => data(api.put(`${team(id)}/drills/${encodeURIComponent(slug)}`, drill))
export const deleteTeamDrill = (id, slug) => data(api.delete(`${team(id)}/drills/${encodeURIComponent(slug)}`))
export const unlinkTeamDrill = (id, slug) => data(api.post(`${team(id)}/drills/${encodeURIComponent(slug)}/unlink`))
export const submitTeamDrill = (id, slug, note) => data(api.post(`${team(id)}/drills/${encodeURIComponent(slug)}/submit`, { note, confirm_own: true }))
export const voteOnDrill = (slug, vote, reason = null) => data(api.put(`/drills/${encodeURIComponent(slug)}/vote`, { vote, reason }))
export const getDrillSuggestions = (id, playerId, periodId, skills) => data(api.get(`${team(id)}/players/${playerId}/drill-suggestions`, { params: { period_id: periodId, skills }, paramsSerializer: { indexes: null } }))
export const getSavedPlan = (id, playerId, periodId) => data(api.get(`${team(id)}/players/${playerId}/plan`, { params: { period_id: periodId } }))
export const generatePlan = (id, playerId, periodId) => data(api.post(`${team(id)}/players/${playerId}/plan`, { period_id: periodId }))
export const getCycles = (id, playerId, periodId) => data(api.get(`${team(id)}/players/${playerId}/cycles`, { params: { period_id: periodId } }))
export const startCycle = (id, playerId, periodId, checkin = []) => data(api.post(`${team(id)}/players/${playerId}/cycles`, { period_id: periodId, checkin }))
export const getPlanAlternatives = (id, playerId, periodId, skillId, slot) => data(api.get(`${team(id)}/players/${playerId}/plan/alternatives`, { params: { period_id: periodId, skill_id: skillId, slot } }))
// change: { action: 'choose' | 'remove' | 'reset', drill?, start_variation_id? }
export const editPlanSlot = (id, playerId, periodId, skillId, slot, change) => data(api.put(`${team(id)}/players/${playerId}/plan/slot`, { period_id: periodId, skill_id: skillId, slot, ...change }))
export const generateSquadPlans = (id, periodId, onlyMissing) => data(api.post(`${team(id)}/plans/generate`, { period_id: periodId, only_missing: onlyMissing }))
export const getDrill = slug => data(api.get(`/drills/${encodeURIComponent(slug)}`))
export const getSkillTags = () => data(api.get('/skill-tags'))
export const getPracticeLibrary = () => data(api.get('/practice/scenarios'))
export const getSessions = (id, periodId) => data(api.get(`${team(id)}/sessions`, { params: periodId ? { period_id: periodId } : {} }))
export const getSessionFocus = (id, periodId) => data(api.get(`${team(id)}/sessions/focus`, { params: { period_id: periodId } }))
export const createSession = (id, session) => data(api.post(`${team(id)}/sessions`, session))
export const getSession = (id, sessionId) => data(api.get(`${team(id)}/sessions/${sessionId}`))
export const updateSession = (id, sessionId, changes) => data(api.patch(`${team(id)}/sessions/${sessionId}`, changes))
export const deleteSession = (id, sessionId) => data(api.delete(`${team(id)}/sessions/${sessionId}`))
export const addSessionBlock = (id, sessionId, block) => data(api.post(`${team(id)}/sessions/${sessionId}/blocks`, block))
export const updateSessionBlock = (id, sessionId, blockId, changes) => data(api.put(`${team(id)}/sessions/${sessionId}/blocks/${blockId}`, changes))
export const deleteSessionBlock = (id, sessionId, blockId) => data(api.delete(`${team(id)}/sessions/${sessionId}/blocks/${blockId}`))
export const getBlockAlternatives = (id, sessionId, blockId) => data(api.get(`${team(id)}/sessions/${sessionId}/blocks/${blockId}/alternatives`))
export const setSessionGroups = (id, sessionId, groups) => data(api.put(`${team(id)}/sessions/${sessionId}/groups`, { groups }))
export const regenerateSession = (id, sessionId) => data(api.post(`${team(id)}/sessions/${sessionId}/regenerate`))
export const makeBlockGroups = (id, sessionId, blockId, count = null) => data(api.post(`${team(id)}/sessions/${sessionId}/blocks/${blockId}/groups`, count ? { count } : {}))
export const setBlockGroups = (id, sessionId, blockId, groups) => data(api.put(`${team(id)}/sessions/${sessionId}/blocks/${blockId}/groups`, { groups }))
export const removeBlockGroups = (id, sessionId, blockId) => data(api.delete(`${team(id)}/sessions/${sessionId}/blocks/${blockId}/groups`))
export const setMatchTeams = (id, sessionId, teams) => data(api.put(`${team(id)}/sessions/${sessionId}/match-teams`, { teams }))
export const suggestMatchTeams = (id, sessionId) => data(api.post(`${team(id)}/sessions/${sessionId}/match-teams/suggest`))
export const getSessionTemplates = id => data(api.get(`${team(id)}/session-templates`))
export const createSessionTemplate = (id, template) => data(api.post(`${team(id)}/session-templates`, template))
export const updateSessionTemplate = (id, templateId, template) => data(api.put(`${team(id)}/session-templates/${templateId}`, template))
export const deleteSessionTemplate = (id, templateId) => data(api.delete(`${team(id)}/session-templates/${templateId}`))
export const setSessionAttendance = (id, sessionId, players) => data(api.put(`${team(id)}/sessions/${sessionId}/attendance`, { players }))
export const getMatrixDraft = id => data(api.get(`${team(id)}/matrix/draft`))
export const saveMatrixDraft = (id, revision, document) => data(api.put(`${team(id)}/matrix/draft`, { revision, document }))
export const publishMatrix = (id, revision, acknowledge, applyToCurrentPeriod) => data(api.post(`${team(id)}/matrix/publish`, { revision, acknowledge, apply_to_current_period: applyToCurrentPeriod }))
export const discardMatrixDraft = id => data(api.delete(`${team(id)}/matrix/draft`))
export const getMatrixVersion = (id, versionId) => data(api.get(`${team(id)}/matrix-versions/${versionId}`))
export const getTeams = () => data(api.get('/teams'))
export const createTeam = name => data(api.post('/teams', { name }))
export const updateTeam = (id, value) => data(api.patch(team(id), value))
export const deleteTeam = (id, confirmName) => data(api.delete(team(id), { data: { confirm_name: confirmName } }))
export const getAuditLog = id => data(api.get(`${team(id)}/audit`))
export const getMembers = id => data(api.get(`${team(id)}/members`))
export const setMemberRole = (id, userId, role) => data(api.patch(`${team(id)}/members/${userId}`, { role }))
export const removeMember = (id, userId) => data(api.delete(`${team(id)}/members/${userId}`))
export const inviteCoach = (id, email) => data(api.post(`${team(id)}/invites`, { email }))
export const getPlayers = id => data(api.get(`${team(id)}/players`))
export const addPlayer = (id, name) => data(api.post(`${team(id)}/players`, { name }))
export const renamePlayer = (id, playerId, name) => data(api.patch(`${team(id)}/players/${playerId}`, { name }))
export const archivePlayer = (id, playerId) => data(api.post(`${team(id)}/players/${playerId}/archive`))
export const restorePlayer = (id, playerId) => data(api.post(`${team(id)}/players/${playerId}/restore`))
// A plain link: the browser downloads it with the session cookie.
export const playerExportUrl = (id, playerId) => `/api${team(id)}/players/${playerId}/export`
export const deletePlayer = (id, playerId, confirmName) => data(api.delete(`${team(id)}/players/${playerId}`, { data: { confirm_name: confirmName } }))
export const getPeriods = id => data(api.get(`${team(id)}/periods`))
// options: { starts_season, groups } — groups maps player id to a U-number (or null) after the new-season review.
export const createPeriod = (id, label, options = {}) => data(api.post(`${team(id)}/periods`, { label, is_active: true, ...options }))
export const getPeriodGroups = (id, periodId) => data(api.get(`${team(id)}/periods/${periodId}/groups`))
export const setPlayerGroup = (id, playerId, periodId, ageGroup) => data(api.put(`${team(id)}/players/${playerId}/group`, { age_group: ageGroup }, { params: { period_id: periodId } }))
export const activatePeriod = (id, periodId) => data(api.post(`${team(id)}/periods/${periodId}/activate`))
export const renamePeriod = (id, periodId, label) => data(api.patch(`${team(id)}/periods/${periodId}`, { label }))
export const deletePeriod = (id, periodId) => data(api.delete(`${team(id)}/periods/${periodId}`))
export const getCoachAssessment = (id, playerId, periodId) => data(api.get(`${team(id)}/assessments/coach`, { params: { player_id: playerId, period_id: periodId } }))
export const submitCoachAssessment = (id, value) => data(api.put(`${team(id)}/assessments/coach`, value))
export const getComparison = (id, playerId, periodId) => data(api.get(`${team(id)}/assessments/compare`, { params: { player_id: playerId, period_id: periodId } }))
export const getPeriodAssessments = (id, periodId) => data(api.get(`${team(id)}/assessments/period/${periodId}`))
export const getInsights = (id, periodId, position, group) => data(api.get(`${team(id)}/insights`, { params: { ...(periodId ? { period_id: periodId } : {}), ...(position ? { position } : {}), ...(group ? { group } : {}) } }))
export const getPlayerHistory = (id, playerId) => data(api.get(`${team(id)}/players/${playerId}/history`))
export const getPlayerProfile = (id, playerId, periodId) => data(api.get(`${team(id)}/players/${playerId}/profile`, { params: { period_id: periodId } }))
export const getRevisions = (id, assessmentId) => data(api.get(`${team(id)}/assessments/${assessmentId}/revisions`))
export const getPriorities = (id, playerId, periodId) => data(api.get(`${team(id)}/priorities`, { params: { player_id: playerId, period_id: periodId } }))
export const setPriorities = (id, playerId, periodId, priorities) => data(api.put(`${team(id)}/priorities`, { priorities }, { params: { player_id: playerId, period_id: periodId } }))
export const issueSelfLink = (id, playerId, periodId) => data(api.post(`${team(id)}/players/${playerId}/periods/${periodId}/self-link`))
export const revokeSelfLink = (id, playerId, periodId) => data(api.delete(`${team(id)}/players/${playerId}/periods/${periodId}/self-link`))
export const getSelfLinkBoard = (id, periodId) => data(api.get(`${team(id)}/periods/${periodId}/self-links`))
export const issueSelfLinks = (id, periodId, playerIds) => data(api.post(`${team(id)}/periods/${periodId}/self-links`, playerIds ? { player_ids: playerIds } : {}))
export const getPlayerReport = (id, playerId, periodId) => data(api.get(`${team(id)}/players/${playerId}/periods/${periodId}/report`))
export const savePlayerReport = (id, playerId, periodId, message) => data(api.put(`${team(id)}/players/${playerId}/periods/${periodId}/report`, { message: message.trim() || null }))
export const shareReport = (id, playerId, periodId) => data(api.post(`${team(id)}/players/${playerId}/periods/${periodId}/report/share`))
export const revokeReportShare = (id, playerId, periodId) => data(api.delete(`${team(id)}/players/${playerId}/periods/${periodId}/report/share`))
export const getSharedReport = token => data(api.get(`/report/${token}`))
export const getSharedReportDrill = (token, slug) => data(api.get(`/report/${encodeURIComponent(token)}/drills/${encodeURIComponent(slug)}`))
export const extendReportShare = (id, playerId, periodId, weeks) => data(api.post(`${team(id)}/players/${playerId}/periods/${periodId}/report/share/extend`, { weeks }))
export const getSelfLinkInfo = token => data(api.get(`/self/${token}`))
export const submitSelfAssessment = (token, value) => data(api.post(`/self/${token}`, value))
