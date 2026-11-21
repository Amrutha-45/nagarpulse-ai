# NagarPulse AI

A Streamlit hackathon MVP for AI-assisted civic grievance triage in Hyderabad.

## Files
- `app.py` — complete application
- `requirements.txt` — Python dependencies

## Run locally
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Set `GEMINI_API_KEY` in your environment, or enter it in the app sidebar. Without a key, the app uses an offline demo fallback; that fallback does not inspect the uploaded image.

## Streamlit Community Cloud
1. Push `app.py` and `requirements.txt` to the root of a GitHub repository.
2. Open https://share.streamlit.io and sign in with GitHub.
3. Choose **Create app**, select the repository, branch, and `app.py`.
4. In **Advanced settings → Secrets**, add:
   ```toml
   GEMINI_API_KEY = "your-key-here"
   ```
5. Deploy and test the public URL.

Never commit API keys to GitHub.

## MVP limitations
- Ticket data is stored in Streamlit session state, not a shared production database. Different visitor sessions will not share new reports; session data can reset.
- Sample tickets and locality-centre coordinates are illustrative.
- Duplicate matching follows the requested MVP rule: same locality + same category + unresolved status.
- No complaint is actually sent to GHMC or another authority.
- Uploaded images are processed in memory and are not persisted.
- Severity and AI outputs are suggestions and require human verification.
