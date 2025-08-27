# Google Chatbot Backend

This is the Python FastAPI backend for the Google Chatbot application.

## Deploy to Render

1. Create a new repository on GitHub with only these backend files
2. Go to [Render.com](https://render.com) and create a new Web Service
3. Connect your GitHub repository
4. Use these settings:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Environment**: Python 3

## Environment Variables

Add these environment variables in Render:

\`\`\`
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
CEREBRAS_API_KEY=your_cerebras_api_key
\`\`\`

## After Deployment

1. Copy your Render URL (e.g., `https://your-app.onrender.com`)
2. Update your frontend's `lib/api.ts` file with this URL
3. Add your Render callback URL to Google Cloud Console:
   `https://your-app.onrender.com/auth/google/callback`

## Local Development

\`\`\`bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
