import os
import requests
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from supabase import create_client, Client
from fastapi.middleware.cors import CORSMiddleware

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Initialize Supabase client
supabase_url = "https://cyniazclgdffjcjhneau.supabase.co"
supabase_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN5bmlhemNsZ2RmZmpjamhuZWF1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYxMTk2MzAsImV4cCI6MjA3MTY5NTYzMH0.QitglJD_9AfzBhB6OMD4LbVUOBurpTh9CFA4r0wQ_Vk"

supabase: Client = create_client(supabase_url, supabase_key)

class TopicRequest(BaseModel):
    topic: str
    days_back: int = 3  # Optional with default value

# Your existing endpoints
@app.get("/")
def read_root():
    return {"message": "Hello World - News API is working!"}

@app.post("/predict")
def predict(input_data: str):
    return {"prediction": input_data}

# ======== NEWS SUMMARIZATION ENDPOINTS ========

# Request model for news summarization
class NewsRequest(BaseModel):
    topic: str
    days_back: Optional[int] = 3
    max_articles: Optional[int] = 5

# Response model
class NewsResponse(BaseModel):
    status: str
    summary: str
    articles_found: int
    topic: str

# Set up API keys - use environment variable for security
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "994cc60dc5f8832509cd540db1c3e00c6df41a99")

def search_news(query, days_back=7):
    """Search for recent news using Serper API"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    search_url = "https://google.serper.dev/search"
    
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    payload = {
        "q": f"{query} after:{start_date.strftime('%Y-%m-%d')}",
        "num": 10
    }
    
    try:
        response = requests.post(search_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {e}")

def manual_analysis(articles, topic):
    """Manual analysis fallback"""
    analysis = f"""# News Analysis Report: {topic}
    
## 📊 Research Overview
Found {len(articles)} recent articles about {topic}.

## 🔍 Key Findings
"""
    
    for i, article in enumerate(articles, 1):
        analysis += f"\n{i}. **{article.get('title', 'No title')}**\n"
        analysis += f"   - Source: {article.get('source', 'Unknown')}\n"
        analysis += f"   - Summary: {article.get('snippet', 'No description')[:100]}...\n"
    
    analysis += "\n## 📚 Sources\n"
    
    for article in articles:
        analysis += f"- [{article.get('title', 'No title')}]({article.get('link', '')})\n"
    
    return analysis

def store_in_supabase(topic, articles):
    """Store search results in Supabase database using the Supabase client"""
    print(f"Attempting to store {len(articles)} articles for topic: {topic}")
    
    try:
        # Insert the search results using Supabase client
        data, count = supabase.table("news_searches").insert({
            "topic": topic,
            "articles_found": len(articles),
            "articles": articles
        }).execute()
        
        print(f"Successfully stored {len(articles)} articles in Supabase!")
        return True
        
    except Exception as e:
        print(f"Supabase error: {e}")
        # If table doesn't exist, create it and try again
        try:
            # Create the table using the Supabase SQL editor functionality
            # Note: You might need to create this table manually in the Supabase dashboard
            # or use the SQL editor to run:
            # CREATE TABLE news_searches (
            #   id SERIAL PRIMARY KEY,
            #   topic VARCHAR(255) NOT NULL,
            #   search_timestamp TIMESTAMP DEFAULT NOW(),
            #   articles_found INTEGER,
            #   articles JSONB
            # );
            print("Table might not exist. Please create it in Supabase dashboard.")
            return False
        except Exception as e2:
            print(f"Failed to create table: {e2}")
            return False

# NEW ENDPOINT: News Summarization
@app.post("/summarize-news", response_model=NewsResponse)
async def summarize_news(request: NewsRequest, background_tasks: BackgroundTasks):
    """Generate news summary for a given topic"""
    try:
        # Search for news
        search_results = search_news(request.topic, request.days_back)
        
        if not search_results or 'organic' not in search_results:
            raise HTTPException(status_code=404, detail="No news articles found")
        
        articles = []
        for item in search_results.get('organic', [])[:request.max_articles]:
            article = {
                'title': item.get('title', 'No title'),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', 'No description'),
                'source': item.get('source', 'Unknown')
            }
            articles.append(article)
        
        # Store results in Supabase in background to avoid blocking
        background_tasks.add_task(store_in_supabase, request.topic, articles)
        
        # Generate summary using manual analysis
        summary = manual_analysis(articles, request.topic)
        
        return NewsResponse(
            status="success",
            summary=summary,
            articles_found=len(articles),
            topic=request.topic
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")

# NEW ENDPOINT: Quick news search
@app.get("/search-news/{topic}")
async def search_news_endpoint(topic: str, days_back: int = 3):
    """Search for news articles only"""
    try:
        search_results = search_news(topic, days_back)
        
        if not search_results or 'organic' not in search_results:
            return {"articles": [], "count": 0}
        
        articles = []
        for item in search_results.get('organic', [])[:5]:
            article = {
                'title': item.get('title', 'No title'),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', 'No description'),
                'source': item.get('source', 'Unknown')
            }
            articles.append(article)
        
        # Store results in Supabase (synchronous to ensure it happens)
        storage_success = store_in_supabase(topic, articles)
        
        return {
            "topic": topic,
            "articles_found": len(articles),
            "storage_success": storage_success,
            "articles": articles
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")

# NEW ENDPOINT: Get search history from Supabase
@app.get("/search-history")
async def get_search_history():
    """Get all previous search results from database"""
    try:
        # Use Supabase client to fetch data
        response = supabase.table("news_searches").select("*").order("search_timestamp", desc=True).limit(20).execute()
        return {"history": response.data}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase error: {str(e)}")

# NEW ENDPOINT: Debug database connection
@app.get("/debug-db")
async def debug_db():
    """Check database connection status"""
    try:
        # Test Supabase connection by making a simple query
        response = supabase.table("news_searches").select("count", count="exact").execute()
        return {
            "status": "connected", 
            "supabase_url": supabase_url,
            "table_count": response.count
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# NEW ENDPOINT: Health check with news API status
@app.get("/health")
async def health_check():
    # Test Supabase connection
    try:
        response = supabase.table("news_searches").select("count", count="exact").limit(1).execute()
        db_status = "connected"
    except Exception as e:
        db_status = f"disconnected: {str(e)}"
    
    return {
        "status": "healthy", 
        "database": db_status,
        "endpoints": {
            "GET /": "Root endpoint",
            "POST /predict": "Prediction endpoint",
            "POST /summarize-news": "News summarization",
            "GET /search-news/{topic}": "News search",
            "GET /search-history": "View search history",
            "GET /debug-db": "Debug database connection",
            "GET /health": "Health check"
        }
    }

# NEW ENDPOINT: Clear search history (for testing)
@app.delete("/clear-history")
async def clear_history():
    """Clear all search history (for testing purposes)"""
    try:
        # Delete all records from the table
        response = supabase.table("news_searches").delete().neq("id", "0").execute()
        return {"status": "success", "message": f"Deleted {len(response.data)} records"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase error: {str(e)}")