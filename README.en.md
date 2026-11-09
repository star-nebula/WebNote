# WebNote · Web-to-Note Workflow

> Turns "collect → classify → distill → verify → confirm" into **a scheduler (main session) + three independent agents**. Deterministic work stays with the scheduler; only what truly needs independent judgment goes to a subagent.

[中文](README.md) · [English](#quick-start)

---

## Quick Start

### First: you can use this with zero setup

The value of this project is the **workflow design and agent definitions**, not the Python scripts. The scripts are accelerators for the collection step — without them, you paste content in manually and the pipeline still runs end to end.

| What you want to process | What you additionally need |
|---|---|
| Text / articles (you supply the content) | **Nothing.** Works right after clone |
| PDF / Word documents | `pip install pypdf python-docx` |
| Text inside images | `pip install rapidocr-onnxruntime` |
| Video / audio speech | `pip install faster-whisper` + `ffmpeg` |
| Image / video visual understanding | the above + `DEEPSEEK_API_KEY` |

Not sure what your machine can do? Run the self-check (standard library only):

```bash
python tools/doctor.py      # what this tool can use, what's missing
python tools/check-env.py   # which media branches work on this machine
```

It prints what works, what's missing, and how to install it. **Missing capabilities only affect their media type** — no ffmpeg means no video, but the text pipeline works fine.

### Three ways to use it

**Path A · Install the skill** (recommended — set up once, triggers naturally)

Copy the project's `skills/` directory into your AI tool's project-level skills dir:

- WorkBuddy / Codex: `<project>/skills/` → `.workbuddy/skills/`、`.codex/skills/`
- Claude Code: `<project>/skills/` → `.claude/skills/`, then `python tools/doctor.py --wire` for roles + write guard
- Tool doesn't support project skills → use Path B

**Path B · One prompt** (no install, works with any AI)

- Tools with subagent support (Claude Code / CodeBuddy / Cursor) → [`prompts/入口提示词-全自动.md`](prompts/入口提示词-全自动.md)
- Plain chat UI (ChatGPT / Claude web) → [`prompts/入口提示词-单对话框.md`](prompts/入口提示词-单对话框.md)

Copy the code block, replace the project path with yours, and send it along with your content.

**Path C · Manual pipeline**

Walk the five steps yourself, pointing the AI at the relevant definition file each time. To see what the output looks like first: [`examples/`](examples/).

> Layering: `webnote-workflow` is the **orchestrator skill**; the three content pipelines live in `skills/image-extract`, `skills/video-extract`, `skills/xhs-note`, loaded by content type during collection. Five-step details: [docs/architecture.md](docs/architecture.md).

---

## Overview

WebNote is a **trust-first** pipeline. Its goal is not to produce notes faster, but to turn web content into knowledge you can actually rely on.

```
Scheduler (your AI tool)
├── 1. Collection      (scheduler itself — rules + CLI tools)
├── 2. Classifier      (subagent — 4-way classification)
├── 3. Distiller       (subagent — key points, each tagged with source type)
├── 4. Verifier        (FRESH subagent — three-state verification)
└── 5. Confirmation    (scheduler itself — proposal, all pending)
```

Only **3 subagents**, not 5 — the scheduler handles the deterministic steps itself.

### Agent definitions are files, not prose

Each agent lives in its own file under `agents/` at the project root, with a frontmatter contract (`context` / `reads` / `writes` / `forbidden`):

```
agents/                       project-root, platform-neutral, single source of truth
├── classifier.md             Classifier — 4-way classification
├── distiller.md              Distiller  — key points + source-type tags
└── verifier.md               Verifier   — three-state check (context: fresh)
skills/webnote-workflow/references/steps/
├── collect.md / collect-image.md / collect-video-audio.md / collect-web-archive.md / confirm.md
                              step cards (no contract), routed by SKILL.md
```

**Hand the definition file to the subagent. Don't paraphrase the role from memory** — paraphrasing drops the hard rules first, and those are exactly the parts that must not be dropped.

`agents/` is a **workflow asset** at the project root; the step cards live in `skills/webnote-workflow/references/steps/`. `skills/webnote-workflow/SKILL.md` is just a router that points to them via project-root-relative paths.

**Registration surfaces (`bot.yaml` → `.claude/`)**: role identity lives in `agents/*.md`; what each tool needs to *register* them (tool allow-list, write scope, whether a fresh context is required) lives in `bot.yaml`. `python tools/doctor.py --wire` generates `.claude/agents/*.md` plus a `PreToolUse` hook in `.claude/settings.json`, so the Verifier's write boundary is **enforced** — an out-of-scope write is rejected by the hook instead of merely discouraged by the prompt. `--check` fails CI if a generated file drifts from the sources.

Nothing there is hand-written, and nothing is copied to a global directory: the role definition always points back to `agents/<name>.md`.

### Execution modes

1. **Mode A · Multi-agent** (recommended): scheduler runs collection + confirmation, spawns 3 independent subagents. The Verifier must be a **fresh context**, never the distiller — an agent cannot audit its own fabrication.
2. **Mode B · Single-dialog** (fallback when subagents aren't available): run collection + classify + distill in one dialog, then **stop** — verification must happen in a **new dialog**. If that's impossible, make the AI write an explicit degradation notice (see `agents/verifier.md`); *an unmarked degradation is a compliant-looking table hiding a real risk*.

### Why verification has three states, not two

The Distiller tags every key point with a **source type**, and the Verifier judges evidence strength from it:

| Source type | Meaning |
|---|---|
| `原文` / `original` | Text extracted by a tool or supplied by you |
| `OCR` | Text recognized from an image / video frame |
| `ASR` | Speech-to-text transcript |
| `Vision` | A model's description of the picture |

Hence three verification states:

| State | Meaning | Safe to store permanently? |
|---|---|---|
| Verified (direct quote) | Found in original text, locatable | Yes |
| Verified (transcribed source) | Found in OCR/ASR/Vision output, not traced back to the raw audio/video | **Review it yourself first** |
| Suspicious / unsupported | No source found, or the note says more than the original | No |

**Why two states fail**: in [`examples/`](examples/) there's a real case. A video note says "62.89 million views", sourced from frame OCR — but the OCR text actually misread "收藏/点赞" as "收款/点费". The numbers came from recognition noise.

With only two states, the Verifier marks it "verified" and buries the caveat in a remarks section — the part you're most likely to skip. That number then enters your knowledge base looking confirmed.

Three states marks it **verified (transcribed source)**, so you know to check the original footage. The note isn't wrong — one link in its evidence chain is model output. You deserve to know that, then decide whether it's worth verifying.

**The entire point of this pipeline is to stop second- or third-hand transcription from masquerading as verified fact.**

### Confirmation boundary

Any delete / archive / publish / long-term-memory write stops at "pending confirmation" — the AI proposes, you press the button.

### License

MIT — see [LICENSE](LICENSE). Design credit: [Axton Liu, "Agent OS 的第一课"](https://www.axtonliu.ai/newsletters/ai-2/posts/agent-os-workstation-division).
