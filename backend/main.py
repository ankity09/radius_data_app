import os
import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime
import json

# Import the existing model serving utilities
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from model_serving_utils import query_endpoint, endpoint_supports_feedback, submit_feedback

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Radius Recycling Chatbot API",
    description="API for Radius Recycling AI Chatbot with Databricks Model Serving",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get serving endpoint from environment
SERVING_ENDPOINT = os.getenv('SERVING_ENDPOINT')
if not SERVING_ENDPOINT:
    # Default to the user's Databricks endpoint
    SERVING_ENDPOINT = "ka-981b9343-endpoint"
    logger.info(f"Using default Databricks endpoint: {SERVING_ENDPOINT}")
else:
    logger.info(f"Using configured Databricks endpoint: {SERVING_ENDPOINT}")

ENDPOINT_SUPPORTS_FEEDBACK = endpoint_supports_feedback(SERVING_ENDPOINT)

# Pydantic models
class ChatMessage(BaseModel):
    message: str
    timestamp: Optional[str] = None

class ChatResponse(BaseModel):
    message: str
    timestamp: str
    request_id: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    serving_endpoint: str
    endpoint_supports_feedback: bool

# In-memory chat history (in production, use a database)
chat_history = []

# --- API Routes ---
@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    logger.info("Health check at /api/health")
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        serving_endpoint=SERVING_ENDPOINT,
        endpoint_supports_feedback=ENDPOINT_SUPPORTS_FEEDBACK
    )

@app.post("/api/chat", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """Send a message to the AI chatbot"""
    try:
        logger.info(f"Received chat message: {message.message[:100]}...")
        
        # Prepare messages for the model serving endpoint
        input_messages = [{
            "role": "user",
            "content": message.message
        }]
        
        # Query the Databricks model serving endpoint
        response_messages, request_id = query_endpoint(
            endpoint_name=SERVING_ENDPOINT,
            messages=input_messages,
            max_tokens=400,
            return_traces=ENDPOINT_SUPPORTS_FEEDBACK
        )
        
        # Extract the assistant's response
        assistant_message = ""
        for msg in response_messages:
            if msg.get("role") == "assistant" and msg.get("content"):
                assistant_message = msg["content"]
                break
        
        if not assistant_message:
            assistant_message = "I'm sorry, I couldn't generate a response. Please try again."
        
        # Create response
        response = ChatResponse(
            message=assistant_message,
            timestamp=datetime.now().isoformat(),
            request_id=request_id
        )
        
        # Store in chat history
        chat_history.append({
            "user_message": message.message,
            "assistant_message": response.message,
            "timestamp": response.timestamp,
            "request_id": response.request_id
        })
        
        # Keep only last 100 messages
        if len(chat_history) > 100:
            chat_history.pop(0)
        
        logger.info(f"Generated response: {response.message[:100]}...")
        return response
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")

@app.get("/api/chat/history")
async def get_chat_history():
    """Get chat history"""
    logger.info("Chat history requested")
    return {"history": chat_history}

@app.delete("/api/chat/history")
async def clear_chat_history():
    """Clear chat history"""
    global chat_history
    chat_history = []
    logger.info("Chat history cleared")
    return {"message": "Chat history cleared"}

@app.post("/api/feedback")
async def submit_chat_feedback(request_id: str, rating: int):
    """Submit feedback for a chat response"""
    try:
        if not ENDPOINT_SUPPORTS_FEEDBACK:
            raise HTTPException(status_code=400, detail="Feedback not supported by this endpoint")
        
        submit_feedback(
            endpoint=SERVING_ENDPOINT,
            request_id=request_id,
            rating=rating
        )
        
        logger.info(f"Feedback submitted for request {request_id}: {rating}")
        return {"message": "Feedback submitted successfully"}
        
    except Exception as e:
        logger.error(f"Error submitting feedback: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error submitting feedback: {str(e)}")

@app.get("/api/dashboard-data")
async def get_dashboard_data():
    """Get dashboard data for charts and metrics"""
    logger.info("Dashboard data requested")
    
    # Mock data - replace with real data from your Databricks workspace
    data = {
        "collections": [
            {"month": "Jan", "value": 1200},
            {"month": "Feb", "value": 1350},
            {"month": "Mar", "value": 1100},
            {"month": "Apr", "value": 1400},
            {"month": "May", "value": 1600},
            {"month": "Jun", "value": 1800}
        ],
        "revenue": [
            {"month": "Jan", "value": 45000},
            {"month": "Feb", "value": 52000},
            {"month": "Mar", "value": 48000},
            {"month": "Apr", "value": 55000},
            {"month": "May", "value": 62000},
            {"month": "Jun", "value": 68000}
        ],
        "metrics": {
            "total_collections": "2,847",
            "active_customers": "1,234",
            "monthly_revenue": "$68,000",
            "efficiency_score": "94.2%"
        }
    }
    
    return data

# --- Static Files Setup ---
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)

app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

# --- Catch-all for React Routes ---
@app.get("/{full_path:path}")
async def serve_react(full_path: str):
    index_html = os.path.join(static_dir, "index.html")
    if os.path.exists(index_html):
        logger.info(f"Serving React frontend for path: /{full_path}")
        return FileResponse(index_html)
    logger.error("Frontend not built. index.html missing.")
    raise HTTPException(
        status_code=404,
        detail="Frontend not built. Please run 'npm run build' first."
    ) 