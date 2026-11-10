# WebNote · Web-to-Note Workflow

> Turns "collect → classify → distill → verify → confirm" into **a scheduler (main session) + three independent agents**. Deterministic work stays with the scheduler; only what truly needs independent judgment goes to a subagent.

[![CI](https://github.com/star-nebula/WebNote/actions/workflows/ci.yml/badge.svg)](https://github.com/star-nebula/WebNote/actions/workflows/ci.yml)

[中文](README.md) · [AI entry](AGENTS.public.md) · [Architecture](docs/architecture.md)

## What this is

A **trust-first** pipeline for turning web content into notes. The goal is not to produce notes faster, but to make sure you can rely on them.

It solves exactly one problem: **stop second- or third-hand transcription from masquerading as verified fact.**

## Quick start

### Zero setup works

The value is the **workflow design and role definitions**, not the Python scripts. Without them you paste content in manually and the pipeline still runs end to end.

| What you process | What you additionally need |
|---|---|
| Text / articles (you supply the content) | **Nothing** |
| PDF / Word | `pip install pypdf python-docx` |
| Text inside images | `pip install rapidocr-onnxruntime` |
| Video / audio speech | `pip install faster-whisper` + `ffmpeg` |
| Image / video understanding | the above + `DEEPSEEK_API_KEY` |

Not sure what your machine can do: `python tools/check-env.py` (standard library only). Missing capabilities only affect their own media type.

### Three ways to use it

| Path | For | How |
|---|---|---|
| **A Install the skill** | Tools with project-level skills | Link `<repo>/skills/` into the tool's skills dir; conversation triggers it naturally afterwards |
| **B One prompt** | Any AI | Hand [`AGENTS.public.md`](AGENTS.public.md) over together with your content |
| **C Manual** | Step-by-step control | Walk [`steps/`](skills/webnote-workflow/steps/), loading `00`–`04` in filename order |

No subagent support (ChatGPT / Claude web): use Mode B, the three-part prompt in [`degraded-single-dialog.md`](skills/webnote-workflow/references/degraded-single-dialog.md). The three parts **must** be three separate conversations — the verifier cannot be the writer.

### Start a run

```bash
cp -r runs/_template runs/2026-11-09-topic     # headers are a contract — don't edit them
```

The five files are filled in order by scheduler / classifier / distiller / verifier / scheduler. Originals are never copied or moved — only their paths are recorded in `00`.

## Why verification has three states, not two

The distiller tags every key point with a **source type** (`原文` / `OCR` / `ASR` / `Vision`); the verifier judges evidence strength from that tag:

| State | Meaning | Safe to store? |
|---|---|---|
| Verified (direct quote) | Found in the original text, locatable | Yes |
| Verified (transcribed source) | Found in OCR/ASR/Vision output, not traced back to the raw audio/video | **Review it yourself** |
| Suspicious | No source found, or the note says more than the original | No |

A real case: a note claimed "62.89 million views", sourced from frame OCR — but the OCR had misread "收藏/点赞" as "收款/点费". With only two states, the verifier marks it "verified" and buries the caveat in a remarks section you are likely to skip. Three states marks it **verified (transcribed source)**: the note isn't wrong, but one link in its evidence chain is model output, and you deserve to know that.

Case study: [`docs/history/`](docs/history/2026-09-03-two-state-example/). **That is an archive with an obsolete format — do not copy its headers.**

## Layout

```
WebNote/
├── AGENTS.public.md      # AI entry (generated from AGENTS.md)
├── bot.yaml              # the one machine-readable fact: upstream of vendored skills
├── skills/               # SKILL.md routes; details live in references/ and steps/
│   ├── webnote-workflow/ #   orchestrator + steps/ pipeline + single-dialog fallback
│   │   └── steps/        #   ★ 00–04: filename order is the pipeline; contracts live here
│   ├── web-archive/      #   lossless archiving of copy-protected / cloud docs
│   ├── image-extract/    #   OCR + visual semantics
│   ├── video-extract/    #   ASR + frame sampling
│   └── browser-skill/    #   vendored external skill (Tencent/BrowserSkill) — don't edit
├── runs/_template/       # ★ five empty skeletons: the only output-format contract
├── tools/                # collection accelerators + self-checks (all deps optional)
├── tests/                # repo invariants (CI) · tests/manual/ needs a real browser
├── docs/                 # architecture · decisions · versions/ · history/ (obsolete, don't copy)
└── .env.example          # env var names only
```

## Execution modes

| Mode | When | Split |
|---|---|---|
| **A Multi-agent** | Tool supports subagents (recommended) | Scheduler does collection + confirmation; three subagents classify / distill / verify; the verifier shares zero context with the distiller |
| **B Single-dialog** | Tool can't open a new session | Collect + classify + distill in one dialog → **stop** → verify in a new conversation → confirm |
| **C Lossless archive** | Copy-protected, cloud docs, login-walled pages | Archive only, no summarizing; distill separately afterwards |

Verification is the safety gate: **an agent cannot audit itself.** If a fresh context is impossible, require the explicit degradation notice in `steps/03-verify.md` — an unmarked degradation is a compliant-looking table hiding a real risk.

## Confirmation boundary

Any delete / archive / publish / long-term-memory write stops at "pending confirmation". The AI may think and propose without limit; anything that *lands* waits for your keypress.

## License

MIT — see [LICENSE](LICENSE). Vendored tool: [BrowserSkill](https://github.com/Tencent/BrowserSkill).
