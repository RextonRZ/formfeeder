# Form Feeder

A command-line tool for generating **labeled bot-submission data to train and evaluate form-filling bot detectors.** Form Feeder uses an LLM to autonomously fill out a form you control, while recording rich telemetry about *how* the form was filled — producing a clean, labeled "bot" class you can pair with real human submissions to build a detection dataset.

Built on [Playwright](https://playwright.dev/) and [Gemini 2.5 Flash](https://deepmind.google/models/gemini/flash/).

---

## What this is for

Automated form submissions are a real problem — survey fraud, fake sign-ups, poll manipulation. Detecting them is hard because a modern LLM produces plausible, in-range, varied *answers*; the content alone is a weak signal. The strong signal is **behavioral and environmental**: how the form was filled, not what was entered.

Form Feeder exists to generate the **bot half of a detection dataset**: realistic automated submissions, fully labeled, captured alongside the telemetry a detector would actually learn from. You pair it with consented human submissions to the same form, train a classifier, and measure how well it separates the two.

### Scope & ethics

- Run the bot **only against forms you own or are explicitly authorized to test.**
- Collect human submissions **with consent**, and store telemetry per your privacy obligations.
- Every record this tool produces is labeled `bot` — it is training data, never meant to be mixed into a live response set or passed off as human.

Using automation to submit responses to forms you don't control corrupts other people's data and violates most platforms' terms of service. This project is for building defenses against that, not for doing it.

---

## A note on instrumentation (read this before you start)

The most discriminative bot-detection features — mouse movement, keystroke cadence, per-field dwell time, scroll behavior — require capturing telemetry **from the client filling the form.** You can't inject that capture into a Google Form you don't host. So there are two collection modes:

- **`google` mode** — fills a real Google Form. You only get *observable* signals: submission timing, inter-submission intervals, and the answer content itself. Thinner, but zero setup.
- **`hosted` mode** (recommended) — point the tool at a small self-hosted form that mirrors your target's structure and ships with the telemetry-capture script bundled in this repo. You control both the bot and the instrumentation, so you get the full behavioral feature set for both classes. This is the mode that produces a serious dataset.

Use the same form for both your bot and human classes so the form itself doesn't become a confound.

---

## Signals captured

In `hosted` mode, each submission record includes:

- **Behavioral** — total time-on-page, per-field dwell and inter-keystroke timing, mouse-movement path features, scroll pattern, field focus/blur order, paste-vs-type events, and corrections (backspaces, re-edits). Across a run, inter-submission intervals.
- **Environmental** — `navigator.webdriver`, plugin/canvas/WebGL fingerprint, timezone-vs-IP consistency, user-agent and automation-flag anomalies.
- **Content** — answer-length distribution, lexical diversity, templated-phrasing markers, cross-response consistency. Included so you can measure how much *weaker* content-only detection is.

In `google` mode, only submission timing and content features are available.

---

## Prerequisites

- Python 3.10+
- A [Gemini API key](https://aistudio.google.com/apikey) (free tier works)
- A form **you own or are authorized to test** — a Google Form (`google` mode) or the bundled self-hosted form (`hosted` mode)

---

## Installation

```bash
pip install git+https://github.com/RextonRZ/formfeeder.git
python -m playwright install chromium
```

---

## Usage

```bash
python -m formfeeder --url "<your-form-url>" --mode <google|hosted> --count <number> --key "<gemini-api-key>"
```

**Example (hosted mode, full telemetry):**

```bash
python -m formfeeder \
  --url "http://localhost:8000/form" \
  --mode hosted \
  --count 50 \
  --key "AIzaSy..."
```

### Flags

| Flag | Required | Description |
|---|---|---|
| `--url` | Yes | URL of a form you own or are authorized to test |
| `--mode` | No | `google` (observable signals only) or `hosted` (full telemetry). Default: `google` |
| `--count` | No | Number of bot submissions to generate (default: `5`) |
| `--key` | No* | Gemini API key — can also be set via `GEMINI_API_KEY` env var |
| `--bot-type` | No | Label tag for this run, e.g. `llm-gemini`, so your dataset can distinguish bot families (default: `llm-gemini`) |
| `--hint` | No | Extra context to vary the synthetic profiles, e.g. `"Respondents are students aged 18–25"` |
| `--debug` | No | Show the browser window while filling so you can watch it work |

*Required if `GEMINI_API_KEY` is not set in your environment.

### Setting the API key as an environment variable

**Windows (PowerShell):**

```powershell
$env:GEMINI_API_KEY = "AIzaSy..."
python -m formfeeder --url "..." --mode hosted --count 50
```

**macOS / Linux:**

```bash
export GEMINI_API_KEY=AIzaSy...
python -m formfeeder --url "..." --mode hosted --count 50
```

---

## Output

Each submission is appended to `runs.jsonl` in your working directory. Every record carries an explicit `label` and the telemetry available for the mode:

```jsonl
{"run_index": 1, "label": "bot", "bot_type": "llm-gemini", "telemetry": {"time_on_page_ms": 4120, "keystroke_count": 0, "mouse_path_points": 0, "navigator_webdriver": true, ...}, "profile": {"age": 22, "occupation": "student"}, "timestamp": 1747123456}
{"run_index": 2, "label": "bot", "bot_type": "llm-gemini", "telemetry": {"time_on_page_ms": 3890, "keystroke_count": 0, "mouse_path_points": 0, "navigator_webdriver": true, ...}, "profile": {"age": 35, "occupation": "engineer"}, "timestamp": 1747123512}
```

Capture your consented human submissions in the same schema with `"label": "human"`, then extract a per-response feature vector for your classifier.

---

## Dataset design tips

- **Hold out whole forms, not rows**, in your test split — so you measure generalization to unseen forms rather than memorization of one.
- **Label by bot family** (`--bot-type`) — collect runs from this LLM tool *and* simpler baselines (naive autofill, record-replay macros) so your detector generalizes beyond one bot.
- **Watch class balance** between bot and human, and across forms.
- **Same form for both classes**, as above, to avoid the form becoming the thing your model actually learns.

---

## Known Limitations

- **Google mode is signal-poor** — without client instrumentation you only get timing and content. For a real detector, use `hosted` mode.
- **Conditional branching** — if a form routes to different sections by answer, some profiles may take an unexpected path. The tool detects this, skips the run, and continues.
- **Gemini free tier rate limit** — ~15 requests/minute on the free tier; large runs will pace themselves.

---

## Updating

```bash
pip install --upgrade git+https://github.com/RextonRZ/formfeeder.git
```

---

## Get a Gemini API Key

Free API keys are available at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
