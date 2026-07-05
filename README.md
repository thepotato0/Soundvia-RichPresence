# Soundvia-RichPresence

Show what you're listening to on [Soundvia](https://soundvia.eu) as a live Discord Rich Presence status.

## Features

- Real-time Discord Rich Presence updates based on your current Soundvia listening activity
- Falls back to an "Idling" status when nothing is playing
- One-time browser login — access tokens are cached and refreshed automatically after that

## Requirements

- Python 3.8+
- The Discord desktop app, running locally
- A Soundvia account and a registered Soundvia application (for API access)

## Installation

```bash
git clone https://github.com/thepotato0/Soundvia-RichPresence.git
cd Soundvia-RichPresence
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root:

```env
APP_TOKEN=your_soundvia_app_token
CLIENT_ID=your_soundvia_client_id
CLIENT_SECRET=your_soundvia_client_secret
REDIRECT_URI=http://localhost:8888/callback
```

| Variable        | Description                                                                     |
|-----------------|-----------------------------------------------------------------------------------|
| `APP_TOKEN`     | Static application token used to verify your app with Soundvia's API              |
| `CLIENT_ID`     | OAuth client ID for your registered Soundvia application                          |
| `CLIENT_SECRET` | OAuth client secret for your registered Soundvia application                      |
| `REDIRECT_URI`  | Callback URL registered with your app — must match exactly, including the port    |

Get these values from your [Soundvia developer dashboard](https://soundvia.eu/developer).

## Running

```bash
python main.py
```

or, if `python` points to Python 2 on your system:

```bash
python3 main.py
```

On first run, a browser window opens asking you to log in and approve access. After that, your token is cached locally and refreshed automatically in the background — you won't be prompted again unless the refresh token itself expires or is revoked.

## How it works

1. Validates `APP_TOKEN` against Soundvia's status endpoint.
2. Authorizes as a user via OAuth (browser login, first run only) to get permission to read your listening activity.
3. Sets an initial "Idling" Discord status.
4. Polls Soundvia roughly every 15 seconds (Discord's Rich Presence rate limit) and updates your status with the current track's title, artist, and cover art.
5. Refreshes the access token automatically if it expires mid-session.

## Todo

- [x] Logging
- [x] Discord RPC
    - [x] Idling status
    - [x] Activity updates based on now listening
- [x] Soundvia API
    - [x] API status
    - [x] Authorization page
    - [x] Token exchange
    - [x] Now listening
- [x] Update README to include new usage method
- [ ] Move hardcoded values to a config.json file

## Troubleshooting

**"Could not find Discord. Is Discord running?"** — make sure the Discord desktop app (not the web version) is open before starting the script.

**Browser doesn't open, or authorization hangs** — check that `REDIRECT_URI` in `.env` exactly matches what's registered for your app on the Soundvia dashboard, including the port.

**Rich Presence isn't updating** — Discord rate-limits activity updates to roughly once every 15 seconds; give it a moment after a track change.