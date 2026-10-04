# prism

## Claude Code plugins

`.claude/settings.json` registers the
[Banana Claude](https://github.com/AgriciDaniel/banana-claude) marketplace,
pinned to `v3.0.0`, and enables the `banana-claude` plugin for this project.
When you open the repo in Claude Code and trust the folder, it asks to install
the plugin.

Banana Claude needs Claude Code 2.1.199+, Python 3.11+ with `python3` on
`PATH`, and a Gemini API key from a billing-enabled Google AI project. Claude
Code asks for the key when the plugin is enabled and stores it as a sensitive
plugin value. Keep keys out of this repository.

Usage:

```text
/banana-claude:banana generate an urban 16:9 hero image with left-side copy space
```

It plans offline first and needs your approval before each paid Gemini request.

To upgrade, change `ref` in `.claude/settings.json` to a newer release tag.
