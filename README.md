# Job-Scout

AI-powered job-search agent. Pulls jobs from Google Jobs every 6 hours, scores
them against your profile with Claude, and emails matches.

## Setup

### 1. Create a private GitHub Gist

Go to [gist.github.com](https://gist.github.com), create a **private** Gist with
a file named `seen_jobs.json` containing `{}`. Copy the Gist ID from the URL
(`gist.github.com/<username>/<gist-id>`).

### 2. Create a GitHub Personal Access Token

Generate a PAT at [github.com/settings/tokens](https://github.com/settings/tokens)
with the `gist` scope. No other scopes needed.

### 3. Configure secrets

Set these environment variables (locally or as GitHub Actions secrets):

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `SERPAPI_KEY` | SerpApi API key (Google Jobs) |
| `RESEND_API_KEY` | Resend API key for email |
| `GITHUB_TOKEN` | PAT with `gist` scope |
| `PROFILE_ENCRYPTION_KEY` | Fernet key for encrypting your profile |

Generate a Fernet key once and save it:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4. Copy and edit config

```bash
cp config.example.yaml config.yaml
# edit config.yaml with your Gist ID, search queries, locations, email addresses
```

### 5. Install and set up your profile

```bash
pip install -e ".[dev]"
scout setup --resume path/to/resume.pdf
```

### 6. Run a dry-run

```bash
scout run --dry-run
```

### 7. Enable the GitHub Actions cron

Push to GitHub and enable the `ci.yml` workflow. The scout will run every 6 hours.
