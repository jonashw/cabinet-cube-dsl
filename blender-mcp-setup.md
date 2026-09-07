# Blender MCP Setup

> **Source:** https://www.blender.org/lab/mcp-server/ — these steps follow
> that page directly. It's the origin of this information; if anything
> here seems out of date, that page is authoritative, not this file.

This is split into its own file (out of `00-cabinet-cube-dsl.md`) because
it's about getting *any* MCP-driven Blender session working at all — it
has nothing to do with the Cabinet Cube DSL specifically, and is a
reasonable candidate to split into its own gist later if it turns out to
be useful on its own.

## 1. Blender

Any recent version.

## 2. The Blender Lab MCP server + add-on

This is a specific project — the official one documented at the page
cited above — not a generic "any Blender MCP server":

```
pip install git+https://projects.blender.org/lab/blender_mcp.git
```

It requires a companion Blender add-on: in Blender, add the extensions
repository `https://lab.blender.org/` (Preferences → Get Extensions →
Repositories), then find and enable the MCP add-on from it.

## 3. Wire it into your MCP client's config

e.g. a project's `.mcp.json` — see [`mcp.json.example`](./mcp.json.example):

```json
{
  "mcpServers": {
    "blender": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/blender_mcp", "blender-mcp"]
    }
  }
}
```

Replace `/absolute/path/to/blender_mcp` with wherever step 2 put it.

**Known failure mode:** if your client reports something like
`Error spawn uv ENOENT` even though `uv` is installed, the subprocess
isn't being spawned through a shell that sources your PATH — replace
`"command": "uv"` with the absolute path from `which uv` (commonly
`~/.local/bin/uv` for the standalone installer). This isn't hypothetical —
it's what happened during this package's own development, and pointing at
the absolute path fixed it immediately.

## 4. Start Blender with the add-on enabled

Then reconnect/restart the `blender` server from your MCP client so it
picks up the config. Confirm it's actually connected before relying on
it — successfully call whatever "list objects in the scene" tool the
server exposes. If that fails, the problem is here, not downstream in
whatever you're trying to build.
