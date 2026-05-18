# formfeeder

Self-configuring Google Form auto-responder powered by Gemini 2.5 Flash.

Point it at any Google Form. It reads the form, figures out the target respondents,
generates diverse personas, and submits realistic responses — automatically.

## Install

```bash
pip install git+https://github.com/YOUR_USERNAME/formfeeder.git
playwright install chromium
```

That's it. No cloning, no config files.

## Usage

```bash
python -m formfeeder \
  --url "https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform" \
  --count 10 \
  --key YOUR_GEMINI_API_KEY
```

Or set your key once as an environment variable so you don't type it every time:

**Windows (PowerShell):**
```powershell
$env:GEMINI_API_KEY="AIza..."
python -m formfeeder --url "..." --count 10
```

**Mac/Linux:**
```bash
export GEMINI_API_KEY=AIza...
python -m formfeeder --url "..." --count 10
```

Optional flags:

| Flag | Description |
|---|---|
| `--hint "..."` | Extra context for the AI (e.g. "UM students aged 18-25") |
| `--debug` | Show the browser window while filling |

## Get a Gemini API key

Free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

## How it works

1. Opens the form in headless Chromium
2. Calls Gemini once to analyze the form — result is cached, so repeat runs skip this step
3. Generates a diverse persona matched to the survey's target demographic
4. Fills each page, clicks Next, repeats until Submit
5. Clicks "Submit another response" and repeats for the full count

Progress is printed to the terminal. Each run is logged to `runs.jsonl` in your current folder.

## Speed

Each response takes roughly **30–90 seconds** depending on how many pages and questions your form has (one Gemini API call per page). For a 5-page form, expect about **10–15 minutes for 10 responses**.

## Known limitations

- **Conditional branching** — if your form routes respondents to different sections based on answers, some personas may trigger a loop. The bot detects this, skips that run, and continues with the next persona.
- **Login-required forms** — the form must be publicly accessible (no Google account required to fill).

## Requirements

- Python 3.10+
- A public Google Form
