const express = require('express');
const router = express.Router();
const { client: redis } = require('../redis');

const DAILY_LIMIT = parseInt(process.env.DAILY_QUOTA || '20', 10);

function todayKey() {
  return `quota:${new Date().toISOString().slice(0, 10)}`;
}

function secondsUntilMidnightUTC() {
  const now = new Date();
  const midnight = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1));
  return Math.floor((midnight - now) / 1000);
}

// GET /api/v1/quota
router.get('/', async (req, res) => {
  try {
    const used = parseInt(await redis.get(todayKey()) || '0', 10);
    const remaining = Math.max(0, DAILY_LIMIT - used);
    res.json({
      used,
      limit: DAILY_LIMIT,
      remaining,
      resetsInSeconds: secondsUntilMidnightUTC()
    });
  } catch (error) {
    console.error('Quota check error:', error.message);
    res.json({ used: 0, limit: DAILY_LIMIT, remaining: DAILY_LIMIT, resetsInSeconds: 86400 });
  }
});

module.exports = { router, DAILY_LIMIT, todayKey, secondsUntilMidnightUTC };
