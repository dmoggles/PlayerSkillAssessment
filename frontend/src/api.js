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
export const register = (email, password) => data(api.post('/auth/register', { email, password }))
export const resendVerification = email => data(api.post('/auth/resend-verification', { email }))
export const verify = token => data(api.post('/auth/verify', { token }))
export const login = (email, password) => data(api.post('/auth/login', { email, password })).then(value => { csrfToken = value.csrf_token; return value })
export const logout = () => data(api.post('/auth/logout')).finally(() => { csrfToken = '' })
export const forgotPassword = email => data(api.post('/auth/forgot-password', { email }))
export const resetPassword = (token, password) => data(api.post('/auth/reset-password', { token, password }))
export const changePassword = (currentPassword, newPassword) => data(api.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword }))
export const acceptInvite = token => data(api.post('/invites/accept', { token }))

export const getSkillTags = () => data(api.get('/skill-tags'))
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
export const getPeriods = id => data(api.get(`${team(id)}/periods`))
export const createPeriod = (id, label) => data(api.post(`${team(id)}/periods`, { label, is_active: true }))
export const activatePeriod = (id, periodId) => data(api.post(`${team(id)}/periods/${periodId}/activate`))
export const renamePeriod = (id, periodId, label) => data(api.patch(`${team(id)}/periods/${periodId}`, { label }))
export const deletePeriod = (id, periodId) => data(api.delete(`${team(id)}/periods/${periodId}`))
export const getCoachAssessment = (id, playerId, periodId) => data(api.get(`${team(id)}/assessments/coach`, { params: { player_id: playerId, period_id: periodId } }))
export const submitCoachAssessment = (id, value) => data(api.put(`${team(id)}/assessments/coach`, value))
export const getComparison = (id, playerId, periodId) => data(api.get(`${team(id)}/assessments/compare`, { params: { player_id: playerId, period_id: periodId } }))
export const getPeriodAssessments = (id, periodId) => data(api.get(`${team(id)}/assessments/period/${periodId}`))
export const getInsights = (id, periodId, position) => data(api.get(`${team(id)}/insights`, { params: { ...(periodId ? { period_id: periodId } : {}), ...(position ? { position } : {}) } }))
export const getPlayerHistory = (id, playerId) => data(api.get(`${team(id)}/players/${playerId}/history`))
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
export const getSelfLinkInfo = token => data(api.get(`/self/${token}`))
export const submitSelfAssessment = (token, value) => data(api.post(`/self/${token}`, value))
