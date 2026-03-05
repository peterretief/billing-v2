# Google Calendar Integration Setup Guide

## Overview
You can now sync your todos directly to Google Calendar. Here's how to set it up.

## Step 1: Get Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Google Calendar API**:
   - Go to APIs & Services > Library
   - Search for "Google Calendar API"
   - Click Enable
4. Create OAuth 2.0 Credentials:
   - Go to APIs & Services > Credentials
   - Click "Create Credentials" > "OAuth 2.0 Client ID"
   - Choose "Web application"
   - Add authorized redirect URIs:
     - `http://localhost:8003/todos/calendar/auth/callback/`
     - `https://yourdomain.com/todos/calendar/auth/callback/` (production)
   - Download the JSON file

## Step 2: Configure Django Settings

Add these environment variables to your `.env` file:

```
GOOGLE_OAUTH_CLIENT_ID=your_client_id_here
GOOGLE_OAUTH_CLIENT_SECRET=your_client_secret_here
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8003/todos/calendar/auth/callback/
```

## Step 3: Set Up Credentials File

1. Download the OAuth credentials JSON from Google Cloud Console
2. Rename it to `google_credentials.json`
3. Place it in the project root directory (`/opt/billing_v2/google_credentials.json`)

## Step 4: Use in Application

### Connect to Google Calendar
1. Go to the Todos list page
2. Click the "Sync Calendar" button
3. You'll be redirected to Google to authorize the app
4. After authorization, you'll be redirected back to your app

### Sync Todos to Calendar
1. Once connected, click "Sync Calendar" to sync all your todos to Google Calendar
2. Your todos will appear as all-day events on the due date

### Filter by Today
- Click the "Today" button on the todo list to see only todos due today

## Features
- ✅ One-click OAuth authentication
- ✅ Sync todos to Google Calendar as events
- ✅ Auto-refresh tokens when expired
- ✅ Store credentials securely in database
- ✅ Filter and manage todos by date

## Troubleshooting

**"OAuth state mismatch"**
- Clear browser cookies and try again

**"Error connecting to Google Calendar"**
- Verify credentials in `.env` file are correct
- Check that `google_credentials.json` exists in project root

**"No todos were synced"**
- Ensure todos have due dates set
- Make sure you're connected to Google Calendar first

## Database Models

### GoogleCalendarCredential
Stores OAuth tokens for each user:
- `user`: The user who connected to Google
- `access_token`: Current OAuth access token
- `refresh_token`: Token to refresh when expired
- `calendar_id`: Google Calendar ID (usually 'primary')
- `sync_enabled`: Whether syncing is enabled
- `token_expiry`: When the access token expires

You can view/manage these in the Django admin at `/admin/todos/googlecalendarcredential/`

## Notes
- Tokens are refreshed automatically when expired
- Only non-cancelled todos are synced
- Synced todos appear as all-day events on their due date
- If no due date is set, the event is created for today
