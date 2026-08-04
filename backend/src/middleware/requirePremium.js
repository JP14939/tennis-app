const { currentTier } = require('../utils/tier');

// Chain after requireAuth (needs req.user.id already set).
function requirePremium(req, res, next) {
  if (currentTier(req.user.id) !== 'premium') {
    return res.status(403).json({
      error: 'This is a Premium feature — upgrade to unlock it.',
      code: 'PREMIUM_REQUIRED',
    });
  }
  next();
}

module.exports = requirePremium;
