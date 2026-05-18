# formfeeder

Self-configuring Google Form auto-responder powered by Gemini 2.5 Flash.

Point it at any Google Form. It reads the form, figures out the target respondents,
generates diverse personas, and submits realistic responses — automatically.

## Install

```bash
pip install git+https://github.com/RextonRZ/formfeeder.git
python -m playwright install chromium
```

That's it. No cloning, no config files.

## Usage

```bash
python -m formfeeder --url "<google form url>" --count <number of responses> --key "<gemini api key>"
```

**Example:**
```bash
python -m formfeeder \
  --url "https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform" \
  --count 20 \
  --key "AIzaSy..."
```

### Optional flags

| Flag | Description |
|---|---|
| `--hint "..."` | Extra context for the AI — use this if the bot generates the wrong type of respondents. E.g. `--hint "Respondents are university students aged 18-25"` |
| `--debug` | Show the browser window while filling so you can watch it work |

**Example with flags:**
```bash
python -m formfeeder \
  --url "https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform" \
  --count 20 \
  --key "AIzaSy..." \
  --hint "University students aged 18-25" \
  --debug
```

### Set your API key as an environment variable (so you don't type it every time)

**Windows (PowerShell):**
```powershell
$env:GEMINI_API_KEY="AIzaSy..."
python -m formfeeder --url "..." --count 20
```

**Mac/Linux:**
```bash
export GEMINI_API_KEY=AIzaSy...
python -m formfeeder --url "..." --count 20
```

## Get a Gemini API key

Free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

## Updating

To get the latest version:

```bash
pip install --upgrade git+https://github.com/RextonRZ/formfeeder.git
```

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
