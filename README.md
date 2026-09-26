# Skills

Agent skills shared across kixelated and moq-dev repositories, for Claude Code
and Codex. Each directory is one skill: `SKILL.md` for both agents, plus
`agents/openai.yaml` for Codex.

Repositories vendor this as a submodule and symlink the skills they use into
`.claude/skills/`, so each repository pins the version it runs.
