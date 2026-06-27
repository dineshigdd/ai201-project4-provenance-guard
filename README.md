## rate limting
"I chose a default limit of 200 per day to accommodate high-volume legitimate creators who might post multiple times throughout the day. I added a tighter limit of 10 per minute as a circuit breaker; this provides enough throughput for a user to batch-upload a few items if needed, but it is low enough to render a automated spam script effectively useless, preventing API exhaustion."


from claud
======
Verification
/submit: 12 rapid calls → 200 × 10, then 429 × 2. ✅
429 returns JSON (via the new error handler), not Flask's default HTML: {"error": "Rate limit exceeded...", "detail": "10 per 1 minute"}. ✅
/health and /log: 15 calls each → all 200, not throttled. ✅ (This is why removing default_limits mattered — a liveness probe hitting /health would otherwise get blocked.)
The limits and why (now in config.py)
SUBMIT_RATE_LIMIT = "200 per day;10 per minute" — moved into Config so it's documented in one place and env-overridable:

10/minute — a real writer submitting their own work never exceeds a handful per minute; a flooding script trips this instantly. Each submit also costs a Groq LLM round-trip, so this protects the upstream API budget too.
200/day — caps sustained single-IP abuse; ~200 pieces/day is already far past realistic human use.
Two notes:

Keyed by client IP (get_remote_address). Behind a reverse proxy you'd want ProxyFix so it sees the real client IP rather than the proxy's — worth a mention in the README's production-caveats.
memory:// storage is per-process — fine for this single-node dev service; a multi-worker deployment would need redis:// so the counter is shared. Both points are good README material for the rate-limiting writeup the assignment asks for.

$ for i in $(seq 1 12); do   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5000/submit     -H "Content-Type: application/json"     -d '{"text": "This is a test submission for rate limit testing purposes only.", "creator_id": "ratelimit-test"}'; done
200
200
200
200
200
200
200
200
200
200
429
429