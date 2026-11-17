# Platform feedback

Friction I hit while building, written the way I would raise it with each platform team.

## MCP Python SDK

- **Major-version rename.** Upgrading to 2.x renamed `FastMCP` to `MCPServer` and moved
  annotation fields to snake_case, while the constructor still accepts the camelCase
  aliases. The import error message pointing at the migration guide was genuinely helpful.
  *Request:* document `list_tools()` (async, return type) and the stdio `run()` call on the
  migration page itself; I had to read signatures from the installed package.

## Claude API

- **Structured outputs fit extraction well:** the response validates against the Pydantic
  schema, so the normaliser only deals with strings it can trust to exist.
- **Confidence is self-reported.** There is no way to get a calibrated per-field
  confidence, which is why I added an independent evidence check against the PDF text.
  *Request:* an example in the docs of grounding extracted fields in the source document.

## Hosting

- **Render:** no free plan for background workers, and pre-deploy commands need a paid
  service, so the free API service runs migrations at start-up. A note in the Blueprint docs
  on the cheapest way to run one web service plus one queue worker would help.
- **Redis billed per command:** a Celery worker polls continuously, which can use up a
  per-command free tier while the app is idle. *Request:* call this out in Celery-with-Redis
  guides.

## Tooling

- **Git Bash on Windows** rewrites arguments that look like Unix paths (`/app/...`) before
  they reach `docker compose exec`. `MSYS_NO_PATHCONV=1` fixes it; it cost a confusing run.
