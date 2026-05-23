# Form Feeder

A command-line tool that automatically fills Google Forms with AI-generated, persona-driven responses. Point it at any public Google Form — formfeeder reads the form, infers the target demographic, generates realistic respondent personas, and submits answers autonomously.

Built on [Playwright](https://playwright.dev/) and [Gemini 2.5 Flash](https://deepmind.google/models/gemini/flash/).

---

## How It Works

1. Opens the form in a headless Chromium browser
2. Makes a single Gemini API call to analyze the form's topic and target respondents (result is cached — repeat runs skip this step)
3. Generates a diverse persona matched to the survey's demographic
4. Fills each page, clicks Next, and repeats until submission
5. Clicks "Submit another response" and loops for the requested count

Progress is printed to the terminal. Each run is appended to `runs.jsonl` in your working directory.

---

## Prerequisites

- Python 3.10+
- A [Gemini API key](https://aistudio.google.com/apikey) (free tier works)
- A publicly accessible Google Form (no login required to fill)

---

## Installation

```bash
pip install git+https://github.com/RextonRZ/formfeeder.git
python -m playwright install chromium
```

No cloning or config files needed.

---

## Usage

```bash
python -m formfeeder --url "<google-form-url>" --count <number> --key "<gemini-api-key>"
```

**Example:**

```bash
python -m formfeeder \
  --url "https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform" \
  --count 20 \
  --key "AIzaSy..."
```

### Flags

| Flag | Required | Description |
|---|---|---|
| `--url` | Yes | Google Form viewform URL |
| `--count` | No | Number of responses to submit (default: `5`) |
| `--key` | No* | Gemini API key — can also be set via `GEMINI_API_KEY` env var |
| `--hint` | No | Extra context for the AI, e.g. `"Respondents are university students aged 18–25"` |
| `--debug` | No | Show the browser window while filling so you can watch it work |

*Required if `GEMINI_API_KEY` is not set in your environment.

### Setting the API key as an environment variable

**Windows (PowerShell):**

```powershell
$env:GEMINI_API_KEY = "AIzaSy..."
python -m formfeeder --url "..." --count 20
```

**macOS / Linux:**

```bash
export GEMINI_API_KEY=AIzaSy...
python -m formfeeder --url "..." --count 20
```

### Using `--hint` to guide persona generation

If the bot generates the wrong type of respondents (e.g. the form description is vague), pass a hint:

```bash
python -m formfeeder \
  --url "https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform" \
  --count 10 \
  --hint "Respondents are postgraduate researchers in Malaysia"
```

---

## Performance

Each response takes roughly **30–90 seconds** depending on form length (one Gemini API call per page). As a rough benchmark, a 5-page form with 10 responses will take approximately **10–15 minutes**.

---

## Output

Each submitted run is appended to `runs.jsonl` in the directory you ran the command from:

```jsonl
{"run_index": 1, "persona": {"age": 22, "occupation": "student", ...}, "timestamp": 1747123456}
{"run_index": 2, "persona": {"age": 35, "occupation": "engineer", ...}, "timestamp": 1747123512}
```

---

## Known Limitations

- **Conditional branching** — if the form routes respondents to different sections based on answers, some personas may trigger an unexpected path. The bot detects this, skips the affected run, and continues with the next persona.
- **Login-required forms** — the form must be publicly accessible without a Google account.
- **Gemini free tier rate limit** — the free tier allows ~15 requests per minute. For large runs, expect some pacing delays.

---

## Updating

```bash
pip install --upgrade git+https://github.com/RextonRZ/formfeeder.git
```

---

## Get a Gemini API Key

Free API keys are available at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
