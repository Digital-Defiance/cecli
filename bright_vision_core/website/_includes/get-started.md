
Install the engine package, then run the CLI or HTTP server.

{% include install.md %}

```bash
# Change directory into your git workspace
cd /path/to/your/project

# CLI
cecli --model sonnet --api-key anthropic=<key>

# Or headless HTTP API (from repo root)
bright-vision-core-serve --workspace /path/to/your/project
```

For the **BrightVision** desktop app, use [bright-vision.digitaldefiance.org](https://bright-vision.digitaldefiance.org/) — it talks to this engine over HTTP.
