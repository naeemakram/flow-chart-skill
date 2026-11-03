# Privacy

flow-chart is a Claude skill that runs on your own machine. It collects nothing.

## What the plugin does with your data

- **No collection.** The plugin has no server, no account and no analytics. Its scripts make no network calls.
- **Your code stays where it is.** Claude reads the files you point it at to work out how they behave, as it does for any request. The plugin itself stores nothing and sends nothing anywhere.
- **What it writes:** a JSON spec and an HTML page, in the folder you choose (usually `docs/`). Nothing else is kept.

## The generated pages

Each HTML page the plugin generates loads its fonts from Google Fonts when someone opens it. Opening a page therefore sends that viewer's browser's usual request (IP address and browser details) to Google, under [Google's privacy policy](https://policies.google.com/privacy). Offline, or if the request is blocked, the page falls back to system fonts and works the same.

## Optional browser check

The optional `check_page.py` script opens a generated page in a local Chromium browser to test it. It talks only to that browser on your machine.

## Contact

Questions or concerns: open an issue at https://github.com/naeemakram/flow-chart-skill/issues
