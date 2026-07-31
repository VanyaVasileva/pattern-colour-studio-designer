# Pattern Colour Studio · Designer Beta

This is a separate private beta. It does not modify or replace the existing
customer-facing Pattern Colour Studio.

## What this beta does

- Upload transparent line art and change both the line and background colours.
- Test flattened two-colour PNG/JPEG artwork with background cleanup.
- Upload coloured motifs on transparency and change only the background.
- Explore 69 curated two-colour combinations across evergreen collections.
- Swap line and background colours or enter exact HEX codes.
- Preview quickly at reduced size.
- Download a lossless PNG and a maximum-quality JPEG at the original uploaded
  pixel dimensions.

The beta does not yet save a permanent designer library, create customer links,
or process subscriptions.

## Recommended input

For the cleanest results, use a transparent PNG:

- **Line + background:** only the line artwork should be visible; the rest of
  the tile should be transparent.
- **Background only:** the coloured motifs should be visible; the surrounding
  background should be transparent.

Flattened two-colour PNG/JPEG files are also supported in line-art mode. Confirm
the original background colour and adjust the cleanup slider only when needed.

The current beta accepts images up to 50 megapixels. A 3000 × 3000 px file is
9 megapixels.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Protect a deployed private beta

Set `DESIGNER_BETA_PASSWORD` in Streamlit's Secrets settings. A template is in
`.streamlit/secrets.toml.example`. When no password is configured, the app opens
without an access-code screen.

Do not commit a real password or customer artwork to a public repository.

## Planned next phase

1. Designer accounts and private pattern storage.
2. Saved pattern settings and designer-owned palette collections.
3. Protected, watermarked customer-preview links.
4. Customer colour-selection submissions routed to the correct designer.
5. Subscription plans and usage limits.
