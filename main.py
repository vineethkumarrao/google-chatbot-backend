from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import json
import requests
from urllib.parse import urlencode
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import uvicorn

app = FastAPI(title="Google Chatbot API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "http://localhost:3002",
        "https://v0-google-integration-chatbot.vercel.app",
        "https://*.v0.app",
        "https://*.vusercontent.net"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")

# Pydantic models
class ChatMessage(BaseModel):
    message: str
    user_id: Optional[str] = None

class AuthResponse(BaseModel):
    auth_url: str

class ChatResponse(BaseModel):
    response: str
    intent: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

# In-memory token storage (use Redis/database in production)
user_tokens = {}

@app.get("/")
async def root():
    return {"message": "Google Chatbot API is running", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "services": ["cerebras", "google-oauth"]}

@app.get("/auth/google")
async def google_auth(request: Request):
    """Initiate Google OAuth flow"""
    try:
        # Get the current domain from the request
        base_url = str(request.base_url).rstrip('/')
        redirect_uri = f"{base_url}/auth/google/callback"
        
        # OAuth 2.0 scopes
        scopes = [
            'openid',
            'email',
            'profile',
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/calendar.readonly',
            'https://www.googleapis.com/auth/drive.readonly'
        ]
        
        # Build authorization URL
        auth_url = (
            f"https://accounts.google.com/o/oauth2/auth?"
            f"client_id={GOOGLE_CLIENT_ID}&"
            f"redirect_uri={redirect_uri}&"
            f"scope={'+'.join(scopes)}&"
            f"response_type=code&"
            f"access_type=offline&"
            f"prompt=consent"
        )
        
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth initiation failed: {str(e)}")

@app.get("/auth/google/callback")
async def google_callback(code: str, request: Request):
    """Handle Google OAuth callback"""
    try:
        base_url = str(request.base_url).rstrip('/')
        redirect_uri = f"{base_url}/auth/google/callback"
        
        # Exchange code for tokens
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        
        token_response = requests.post(token_url, data=token_data)
        tokens = token_response.json()
        
        if "access_token" not in tokens:
            raise HTTPException(status_code=400, detail="Failed to get access token")
        
        # Get user info
        user_info_response = requests.get(
            f"https://www.googleapis.com/oauth2/v2/userinfo?access_token={tokens['access_token']}"
        )
        user_info = user_info_response.json()
        
        # Store tokens (use proper database in production)
        user_id = user_info.get("id")
        user_tokens[user_id] = tokens
        
        # Redirect back to frontend with success
        frontend_url = "https://v0-google-integration-chatbot.vercel.app"
        return RedirectResponse(url=f"{frontend_url}?auth=success&user_id={user_id}")
        
    except Exception as e:
        frontend_url = "https://v0-google-integration-chatbot.vercel.app"
        return RedirectResponse(url=f"{frontend_url}?auth=error&message={str(e)}")

@app.get("/auth/status")
async def auth_status(user_id: str):
    """Check authentication status"""
    if user_id in user_tokens:
        return {"connected": True, "services": ["gmail", "calendar", "drive"]}
    return {"connected": False, "services": []}

@app.post("/chat")
async def chat(message: ChatMessage):
    """Process chat message with Cerebras AI"""
    try:
        # Call Cerebras API
        headers = {
            "Authorization": f"Bearer {CEREBRAS_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama3.1-8b",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that can access Google services like Gmail, Calendar, and Drive. Analyze user requests and provide helpful responses."},
                {"role": "user", "content": message.message}
            ],
            "max_tokens": 500,
            "temperature": 0.7
        }
        
        response = requests.post(
            "https://api.cerebras.ai/v1/chat/completions",
            headers=headers,
            json=payload
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Cerebras API error: {response.text}")
        
        result = response.json()
        ai_response = result["choices"][0]["message"]["content"]
        
        # Simple intent detection
        intent = None
        if any(word in message.message.lower() for word in ["email", "mail", "gmail"]):
            intent = "gmail"
        elif any(word in message.message.lower() for word in ["calendar", "schedule", "meeting"]):
            intent = "calendar"
        elif any(word in message.message.lower() for word in ["drive", "file", "document"]):
            intent = "drive"
        
        return ChatResponse(response=ai_response, intent=intent)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")

@app.get("/google/gmail")
async def get_gmail_messages(user_id: str, limit: int = 10):
    """Get Gmail messages"""
    try:
        if user_id not in user_tokens:
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        tokens = user_tokens[user_id]
        credentials = Credentials(token=tokens["access_token"])
        
        service = build('gmail', 'v1', credentials=credentials)
        results = service.users().messages().list(userId='me', maxResults=limit).execute()
        messages = results.get('messages', [])
        
        email_list = []
        for msg in messages[:5]:  # Limit to 5 for demo
            message = service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = message['payload'].get('headers', [])
            
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
            
            email_list.append({
                'id': msg['id'],
                'subject': subject,
                'sender': sender,
                'snippet': message.get('snippet', '')
            })
        
        return {"emails": email_list}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gmail access failed: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
