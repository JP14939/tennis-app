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

// Stopgap until a real domain is verified in Resend (see STATUS.md /
// TODO_MANUAL.md): the shared sandbox sender can only deliver to the
// account owner's own verified address, so a reset link sent straight to
// toEmail would silently fail to arrive for anyone but Jack. Redirect the
// actual send to Jack's inbox instead, with the real requester's address in
// the subject/body so he can forward the link by hand -- the caller (the
// /auth/forgot-password route) still responds 204 either way, so the
// requesting user never sees anything different. Remove this redirect once
// a verified sending domain makes direct delivery to toEmail work.
const PASSWORD_RESET_REDIRECT_EMAIL = 'jack.p14370@gmail.com';

function sendPasswordResetEmail(toEmail, resetUrl) {
  return sendEmail({
    to: PASSWORD_RESET_REDIRECT_EMAIL,
    subject: `[RallyMax password reset] for ${toEmail}`,
    html: `
      <p>Password reset requested for <strong>${toEmail}</strong> (redirected here -- no verified sending domain yet).</p>
      <p><a href="${resetUrl}">Reset link</a> (expires in 1 hour). Forward it to them if needed.</p>
    `,
  });
}

module.exports = { sendEmail, sendPasswordResetEmail };
