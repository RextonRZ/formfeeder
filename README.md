# Form Feeder

A command-line benchmark for measuring how well a large language model can **read and complete a structured Google Form**. Point it at a form *you own*, and Form Feeder reads the questions, generates synthetic respondent profiles, and submits AI-generated answers — so you can study how coherently and consistently the model fills out real-world forms.

Built on [Playwright](https://playwright.dev/) and [Gemini 2.5 Flash](https://deepmind.google/models/gemini/flash/).

---

## Intended Use & Scope

This is a **capability-evaluation tool**, not a survey-stuffing tool.

- Run it **only against Google Forms you own or have explicit permission to test.**
- Every submission is **AI-generated synthetic data**, logged as such. It is not meant to imitate real human respondents or be mixed into a live dataset.
- Use it to answer questions like: *Can the model parse this form correctly? Does it produce valid, in-range answers? Does it stay consistent with the persona it was given? How does it handle multi-page forms or conditional logic?*

Submitting machine-generated responses to forms you don't control — surveys, polls, sign-ups, contests — corrupts other people's data and typically violates Google's Terms of Service. Don't do it. This project exists to benchmark the model, not to deceive a form owner.

---

## How It Works

1. Opens your form in a headless Chromium browser.
2. Makes a single Gemini API call to parse the form's structure and questions (result is cached — repeat runs skip this step).
3. Generates a **labeled synthetic respondent profile** to act as a test fixture for the run.
4. Fills each page, clicks Next, and repeats until submission.
5. Clicks "Submit another response" and loops for the requested count.

Progress is printed to the terminal. Each run is appended to `runs.jsonl` in your working directory, flagged as synthetic.

---

## Prerequisites

- Python 3.10+
- A [Gemini API key](https://aistudio.google.com/apikey) (free tier works)
- A Google Form **you own or are authorized to test**, publicly accessible (no login required to fill)

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
python -m formfeeder --url "<your-google-form-url>" --count <number> --key "<gemini-api-key>"
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
| `--url` | Yes | Viewform URL of a Google Form you own or are authorized to test |
| `--count` | No | Number of synthetic responses to generate (default: `5`) |
| `--key` | No* | Gemini API key — can also be set via `GEMINI_API_KEY` env var |
| `--hint` | No | Extra context to steer the synthetic profiles, e.g. `"Test respondents are university students aged 18–25"` |
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

### Using `--hint` to steer synthetic profiles

If you want the test fixtures to reflect a particular type of respondent — useful when you're checking how the model handles a specific phrasing or audience — pass a hint:

```bash
python -m formfeeder \
  --url "https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform" \
  --count 10 \
  --hint "Test respondents are postgraduate researchers in Malaysia"
```

---

## Performance

Each response takes roughly **30–90 seconds** depending on form length (one Gemini API call per page). As a rough benchmark, a 5-page form with 10 responses takes approximately **10–15 minutes**.

---

## Output

Each run is appended to `runs.jsonl` in the directory you ran the command from. Entries are explicitly marked as synthetic so they're never mistaken for genuine responses:

```jsonl
{"run_index": 1, "synthetic": true, "profile": {"age": 22, "occupation": "student", ...}, "timestamp": 1747123456}
{"run_index": 2, "synthetic": true, "profile": {"age": 35, "occupation": "engineer", ...}, "timestamp": 1747123512}
```

---

## Known Limitations

- **Conditional branching** — if the form routes respondents to different sections based on answers, some profiles may trigger an unexpected path. The tool detects this, skips the affected run, and continues with the next profile.
- **Login-required forms** — the form must be accessible without a Google account.
- **Gemini free tier rate limit** — the free tier allows ~15 requests per minute. For large runs, expect some pacing delays.

---

## Updating

```bash
pip install --upgrade git+https://github.com/RextonRZ/formfeeder.git
```

---

## Get a Gemini API Key

Free API keys are available at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
