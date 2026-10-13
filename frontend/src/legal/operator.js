// Who runs the service, as the legal pages name it: a sole trader, so the controller is that person. Fill in every [bracketed] value before the 1.0 release;
// tests/legal.test.mjs lists any that are left.
export const OPERATOR = {
  name: 'Dmitry Mogilevsky',
  tradingName: 'TapLine',
  address: 'Unit A, 82 James Carter Road, Mildenhall Industrial Estate, Mildenhall, Suffolk IP28 7DE',
  icoNumber: '[ICO REGISTRATION NUMBER]',
  email: '[PRIVACY CONTACT EMAIL]',
}

// Companies that handle data for us (sub-processors). Clubs are told before this list changes.
export const PROCESSORS = [
  { name: '[VPS PROVIDER]', role: 'Hosts the servers the app and its database run on', where: '[COUNTRY]' },
  { name: '[BACKUP SERVER PROVIDER]', role: 'Hosts the second server that keeps encrypted backups', where: '[COUNTRY]' },
  { name: 'Resend', role: 'Delivers the app’s emails: sign-in, password and invitation links', where: 'Sent from the EU (Ireland); a US company' },
]

export const UPDATED = '13 October 2026'
