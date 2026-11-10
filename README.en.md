# WebNote · Web-to-Note Workflow

> Turns "collect → distill → verify → confirm" into **a scheduler (main session) + two independent agents**. Deterministic work stays with the scheduler; only what truly needs independent judgment goes to a subagent.

[![CI](https://github.com/star-nebula/WebNote/actions/workflows/ci.yml/badge.svg)](https://github.com/star-nebula/WebNote/actions/workflows/ci.yml)

[中文](README.md) · [AI entry](AGENTS.md) · [Architecture](docs/architecture.md)

## What this is

A **trust-first** pipeline for turning web content into notes. The goal is not to produce notes faster, but to make sure you can rely on them.

It solves exactly one problem: **stop second- or third-hand transcription from masquerading as verified fact.**

## Quick start

### Zero setup works

The core value is the **workflow design and the step contracts**, not the Python scripts. Without them you paste the content in manually and the pipeline still runs end to end.

| What you process | What you additionally need |
|---|---|
| Text / articles (you supply the content) | **Nothing** |
| PDF / Word | `pip install pypdf python-docx` |
| Text inside images | `pip install rapidocr-onnxruntime` |
| Video / audio speech | `pip install faster-whisper` + `ffmpeg` |
| Image / video understanding | the above + `DEEPSEEK_API_KEY` |

Not sure what your machine can do: `python tools/check-env.py` (standard library only, run it before installing anything). Missing capabilities only affect their own media type.

### Three ways to use it

| Path | For | How |
|---|---|---|
| **A Install the skill** | Tools with project-level skills | Link `<repo>/skills/` into the tool's skills dir; conversation triggers it naturally afterwards |
| **B One prompt** | Any AI | Hand [`AGENTS.md`](AGENTS.md) over together with your content |
| **C Manual** | Step-by-step control | Walk [`steps/`](skills/webnote-workflow/steps/), loading `00`–`04` in filename order, one file per step |

No subagent support (ChatGPT / Claude web): use Mode B, the three-part prompt in [`mode-b-single-dialog.md`](skills/webnote-workflow/mode-b-single-dialog.md). The three parts **must** be three separate conversations — the verifier cannot be the writer.

### Start a run

```bash
cp -r runs/_template runs/2026-11-09-topic     # headers are a contract — don't edit them
# when done, move the whole run into runs/_archive/ (contents stay out of git)
```

The five files are filled in order by scheduler / classifier / distiller / verifier / scheduler. Originals are never copied or moved — only their paths are recorded in `00`. Anything that went wrong during the run goes into that run's `## 运行异常` section in `00`; the same failure twice should become a test.

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
├── AGENTS.md             # AI entry (auto-loaded under this name); public, tracked
├── AGENTS.local.md       # private overlay (machine facts / preferences; gitignored, not in this tree)
├── bot.yaml              # the one machine-readable fact: upstream of vendored skills
├── skills/               # SKILL.md routes only; pipeline detail in steps/, per-skill data in references/
│   ├── webnote-workflow/ #   orchestrator + steps/ pipeline + Mode B prompt
│   │   ├── mode-b-single-dialog.md  # three-part prompt when subagents are impossible
│   │   └── steps/        #   ★ 00–04: filename order is the pipeline; contracts live here
│   │       └── branches/ #     collection branches: image / video-audio / web-archive
│   ├── web-archive/      #   lossless archiving of copy-protected / cloud docs
│   ├── image-extract/    #   OCR + visual semantics
│   ├── video-extract/    #   ASR + frame sampling
│   └── browser-skill/    #   vendored external skill (Tencent/BrowserSkill) — don't edit
├── runs/
│   ├── _template/        # ★ five empty skeletons: the only output-format contract, read-only
│   └── YYYY-MM-DD-topic/ #   one run (local, never committed)
├── tools/                # collection accelerators + self-checks (all deps optional)
│   ├── check-env.py      #   environment self-check
│   ├── check-links.py    #   relative Markdown links
│   ├── check_vendor.py   #   is the vendored copy still the upstream one (--pull to refresh)
│   └── extract-*.py      #   document / web / video / image extraction
├── tests/                # repo invariants (CI)
│   └── manual/           #   real-browser regressions + offline fixtures (not in CI)
├── docs/
│   ├── architecture.md   # current architecture
│   ├── decisions.md      # decision log
│   ├── versions/         # published earlier versions (text kept as published)
│   └── history/          # archive: obsolete formats, kept only to explain where rules came from
├── .github/workflows/    # CI: pytest → vendored skill → compileall → links
├── .githooks/pre-push    # local pre-push self-check (see below)
├── .gitattributes        # no text conversion for the vendored copy (--online relies on it)
├── requirements-dev.txt  # pytest and PyYAML only
├── LICENSE               # MIT
└── README.en.md          # this file (mirrors the Chinese version)
```

## Execution modes

| Mode | When | Split |
|---|---|---|
| **A Multi-agent** | Tool supports subagents (recommended) | Scheduler does collection + confirmation; two subagents distill and verify; the verifier shares zero context with the distiller |
| **B Single-dialog** | Tool can't open a new session | Collect + distill in one dialog → **stop** → verify in a new conversation → confirm |
| **C Lossless archive** | Copy-protected, cloud docs, login-walled pages | Archive only, no summarizing; distill separately afterwards |

Verification is the safety gate: **an agent cannot audit itself.** If a fresh context is impossible, declare the degradation explicitly as `steps/02-verify.md` requires — an unmarked degradation is a compliant-looking table hiding a real risk.

## Confirmation boundary

The AI produces a proposal; you press the key. The test: **if this action is wrong, can it be undone?**

| Must stop at "pending confirmation" | The scheduler may do directly |
|---|---|
| Delete / archive / move material | Classify URLs, call CLI tools, read and distill |
| Publish (article / social post) | List items, write proposals, give advice |
| Write to long-term memory / the knowledge base | — |

**The AI may think and propose without limit; anything that *lands* waits behind this gate.**

## Development environment

- **Test dependencies are declared**: `pip install -r requirements-dev.txt` (only `pytest` and `PyYAML`; the tools themselves are mostly standard library). CI uses it as the cache key.
- **Pre-push self-check**: run `git config core.hooksPath .githooks` once; every push then runs pytest / vendored-skill / link checks first (about 3 seconds, offline). Skip with `git push --no-verify` when in a hurry.
- Machine-specific settings (dedicated ASR venv, local model snapshots, which git binary is used for pushing) are not part of the shared contract; they live in the untracked `AGENTS.local.md`.

### Environment variables

Three optional keys; missing ones only disable their own media type. **This repo does not load `.env`** — inject them through the shell (`export`, or `setx` on Windows then reopen the terminal).

| Key | Read by | Needed when |
|---|---|---|
| `DEEPSEEK_API_KEY` | `tools/ds_vision.py` | Image / video frame understanding |
| `OCR_PYTHON` | `tools/extract-image-ocr.py`, `extract-video-frames.py` | RapidOCR installed in a separate interpreter |
| `GITHUB_TOKEN` | `tools/check_vendor.py --online` | No `gh` installed, to avoid anonymous rate limits (403) |

## License

MIT — see [LICENSE](LICENSE). Vendored tool: [BrowserSkill](https://github.com/Tencent/BrowserSkill) (Tencent, open source).
