# Wordle Backend API

- Swagger docs: /docs
- Health: GET /api/health/
- Auth:
  - POST /api/auth/register/ {username,email,password}
  - POST /api/auth/login/ {username,password}
  - POST /api/auth/logout/
  - POST /api/auth/password-reset/ {email}
  - POST /api/auth/password-reset-confirm/ {uid,token,new_password}
- Gameplay:
  - POST /api/game/new/ {max_attempts?}
  - GET /api/game/current/
  - POST /api/game/guess/?game_id? {guess}
  - GET /api/game/reveal/?game_id={id}
- Profile:
  - GET /api/me/
  - GET /api/me/history/?limit=20
- Leaderboard:
  - GET /api/leaderboard/?type=streak|win_rate|fastest|best_attempts&limit=20
- Effects:
  - POST /api/effects/trigger/ {effect, context?}

Notes:
- Session authentication via Django sessions. Ensure CSRF handled if using browser forms; for SPA, configure CSRF header/cookie.
- Dev email backend prints password reset emails to console.
