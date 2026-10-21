# PinPilot 🚀

**Automated Pinterest → Gumroad Digital Product Pipeline**

PinPilot watches your Dropbox folder for new product assets, generates Pinterest Pins with optimized titles/descriptions, publishes them via the Pinterest API, and links each Pin to your Gumroad product listing.

## Architecture

```
Dropbox (product images/PDFs)
        │
        ▼
   PinPilot (Python)
   ├── Fetch new files from Dropbox
   ├── Generate Pin metadata (title, description, hashtags)
   ├── Validate & deduplicate
   ├── Publish Pin via Pinterest API
   └── Log results & track performance
        │
        ▼
  Gumroad (product listing page)
```

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Get your API keys

#### Dropbox
1. Go to https://www.dropbox.com/developers/apps
2. Create a new app (Scoped access → Full Dropbox or App folder)
3. Generate an access token
4. Copy the **App Key**, **App Secret**, and **Access Token**

#### Pinterest
1. Go to https://developers.pinterest.com/
2. Create a new app
3. Request access to the Pins API
4. Generate an access token with `pins:read`, `pins:write`, `boards:read`, `boards:write` scopes

#### Gumroad
1. Your Gumroad product URL is all you need (e.g., `https://yourname.gumroad.com/l/product-id`)
2. Optionally, get an API key from https://app.gumroad.com/settings/advanced for tracking

### 3. Configure environment
```bash
copy .env.example .env
```
Edit `.env` with your API keys and settings.

### 4. Organize your Dropbox folder
```
/PinPilot/
├── products/
│   ├── dev-job-kit/
│   │   ├── pin-image-1.png        (1000x1500 recommended)
│   │   ├── pin-image-2.png
│   │   └── product.json           (metadata: title, description, gumroad_url, tags)
│   ├── budget-tracker/
│   │   ├── pin-image-1.png
│   │   └── product.json
│   └── ...
└── published/                     (PinPilot moves processed files here)
```

### 5. Run
```bash
# One-time publish
python main.py publish

# Dry run (preview what would be published)
python main.py publish --dry-run

# Check status of published pins
python main.py status

# Schedule automatic publishing (every 6 hours)
python main.py schedule --interval 6

# Validate all product folders
python main.py validate
```

## Product Metadata Format (product.json)

```json
{
  "title": "Developer Job Hunt Kit — Application Tracker & Interview Prep",
  "description": "Land your dream dev job! Includes job application tracker, interview prep checklist, STAR story worksheets, and recruiter outreach templates.",
  "gumroad_url": "https://yourname.gumroad.com/l/dev-job-kit",
  "tags": ["job search", "developer", "resume", "interview prep", "career"],
  "board": "Career Resources",
  "price": "$9",
  "variations": [
    {
      "pin_title": "Stop losing track of job applications 📋",
      "pin_description": "This developer job tracker keeps every application, interview, and follow-up organized. Free yourself from spreadsheet chaos."
    },
    {
      "pin_title": "Interview prep checklist for developers 🎯",
      "pin_description": "Nail your next tech interview with this structured preparation kit. Covers behavioral, technical, and system design rounds."
    }
  ]
}
```

## Free Tier Limits

| Service | Free Limit | PinPilot Usage |
|---------|-----------|----------------|
| Dropbox | 2 GB storage | Plenty for images/PDFs |
| Pinterest API | 1000 calls/day | ~50 pins/day is safe |
| Gumroad | No monthly fee | 10% + $0.50 per sale |

## License
MIT
