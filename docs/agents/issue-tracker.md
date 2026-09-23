# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

> **为什么从 GitHub 模式改成本地模式**（2026-09-23 变更）：
> 原配置用 `gh` CLI 操作 GitHub issues，存在两层阻塞——
> ① `gh` 需读取 `~/.config/gh/hosts.yml`，该路径在 agent 沙箱之外，每次调用都要人工批准；
> ② 配置时 `gh auth status` 已报告 `eicon-xyz` 的 token 失效。
> 本地 Markdown 模式零网络、零凭据依赖，`to-spec` / `to-tickets` 可在沙箱内完整执行。
> 若日后白名单与 token 均已解决，可改回 GitHub 模式
> （模板见 `setup-matt-pocock-skills/issue-tracker-github.md`）。

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`, never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` (the Notes / Decisions-so-far / Fog body).
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.
