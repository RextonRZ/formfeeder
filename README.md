# formfeeder

Self-configuring Google Form auto-responder powered by Gemini 2.5 Flash.

Point it at any Google Form. It reads the form, figures out the target respondents,
generates diverse personas, and submits realistic responses — automatically.

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/formfeeder
cd formfeeder
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
python run.py \
  --url "https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform" \
  --count 10 \
  --key YOUR_GEMINI_API_KEY
```

Or set your key once as an environment variable:

```bash
export GEMINI_API_KEY=AIza...
python run.py --url "..." --count 10
```

Optional `--hint` for extra context:

```bash
python run.py --url "..." --count 5 --hint "University students aged 18-25"
```

## Get a Gemini API key

Free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

## How it works

1. Opens the form in headless Chromium
2. Calls Gemini once to analyze the form (cached — subsequent runs are instant)
3. Generates a diverse persona matched to the survey's target demographic
4. Fills each page, clicks Next, repeats until Submit
5. Clicks "Submit another response" and repeats for the full count

Run log saved to `runs.jsonl`.

## Requirements

- Python 3.10+
- A public Google Form (no sign-in required)