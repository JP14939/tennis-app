// Thin wrapper around Resend's REST API -- same bare-fetch pattern
// routes/billing.js already uses for RevenueCat. No email-sending
// capability existed in this app before the self-serve password reset
// flow (2026-08-20); Resend was chosen for its simple API and generous
// free tier over SendGrid/AWS SES.
//
// RESEND_FROM_EMAIL: Resend's shared sandbox sender works immediately for
// testing but can only send to the account owner's own verified email
// until a real domain is verified in Resend's dashboard (DNS records) --
// see TODO_MANUAL.md for the setup checklist.
const RESEND_API_URL = 'https://api.resend.com/emails';

async function sendEmail({ to, subject, html }) {
  const apiKey = process.env.RESEND_API_KEY;
  const from = process.env.RESEND_FROM_EMAIL;
  if (!apiKey || !from) {
    const err = new Error('Email sending not configured (RESEND_API_KEY/RESEND_FROM_EMAIL missing)');
    err.notConfigured = true;
    throw err;
  }

  const response = await fetch(RESEND_API_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ from, to, subject, html }),
  });

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`Resend API error ${response.status}: ${body}`);
  }
}

function sendPasswordResetEmail(toEmail, resetUrl) {
  return sendEmail({
    to: toEmail,
    subject: 'Reset your RallyMax password',
    html: `
      <p>We got a request to reset your RallyMax password.</p>
      <p><a href="${resetUrl}">Click here to set a new password</a> (link expires in 1 hour).</p>
      <p>If you didn't request this, you can safely ignore this email.</p>
    `,
  });
}

module.exports = { sendEmail, sendPasswordResetEmail };
