import os
import requests
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
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

# Supabase configuration
SUPABASE_URL = "https://cyniazclgdffjcjhneau.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN5bmlhemNsZ2RmZmpjamhuZWF1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYxMTk2MzAsImV4cCI6MjA3MTY5NTYzMH0.QitglJD_9AfzBhB6OMD4LbVUOBurpTh9CFA4r0wQ_Vk"

# Headers for Supabase API requests
supabase_headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

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
    """Store search results in Supabase database using REST API"""
    print(f"Attempting to store {len(articles)} articles for topic: {topic}")
    
    try:
        # Prepare the data for insertion
        data = {
            "topic": topic,
            "articles_found": len(articles),
            "articles": articles
        }
        
        # Make the API request to Supabase
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/news_searches",
            headers=supabase_headers,
            json=data
        )
        
        if response.status_code == 201:
            print(f"Successfully stored {len(articles)} articles in Supabase!")
            return True
        else:
            print(f"Supabase API error: {response.status_code} - {response.text}")
            
            # If table doesn't exist, try to create it
            if response.status_code == 404:
                print("Table might not exist. Creating it now...")
                create_table_success = create_supabase_table()
                if create_table_success:
                    # Retry the insertion
                    response = requests.post(
                        f"{SUPABASE_URL}/rest/v1/news_searches",
                        headers=supabase_headers,
                        json=data
                    )
                    if response.status_code == 201:
                        print(f"Successfully stored after creating table!")
                        return True
            
            return False
        
    except Exception as e:
        print(f"Supabase API error: {e}")
        return False

def create_supabase_table():
    """Create the news_searches table in Supabase using the SQL API"""
    try:
        # This requires the service_role key, which has more permissions
        # For security, you should create the table manually in the Supabase dashboard
        
        print("Please create the 'news_searches' table manually in Supabase dashboard.")
        print("You can use this SQL:")
        print("""
        CREATE TABLE news_searches (
            id SERIAL PRIMARY KEY,
            topic VARCHAR(255) NOT NULL,
            search_timestamp TIMESTAMPTZ DEFAULT NOW(),
            articles_found INTEGER,
            articles JSONB
        );
        """)
        
        return False
        
    except Exception as e:
        print(f"Table creation error: {e}")
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
        # Use Supabase REST API to fetch data
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/news_searches?select=*&order=search_timestamp.desc&limit=20",
            headers=supabase_headers
        )
        
        if response.status_code == 200:
            return {"history": response.json()}
        else:
            return {"history": [], "error": f"API returned {response.status_code}"}
        
    except Exception as e:
        return {"history": [], "error": str(e)}

# NEW ENDPOINT: Debug database connection
@app.get("/debug-db")
async def debug_db():
    """Check database connection status"""
    try:
        # Test Supabase connection by making a simple query
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/news_searches?select=count",
            headers=supabase_headers
        )
        
        if response.status_code == 200:
            return {
                "status": "connected", 
                "supabase_url": SUPABASE_URL,
                "table_exists": True
            }
        else:
            return {
                "status": "connected but table might not exist", 
                "supabase_url": SUPABASE_URL,
                "table_exists": False,
                "error": f"HTTP {response.status_code}"
            }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# NEW ENDPOINT: Health check with news API status
@app.get("/health")
async def health_check():
    # Test Supabase connection
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/news_searches?select=count",
            headers=supabase_headers
        )
        db_status = "connected" if response.status_code == 200 else f"connected but table might not exist ({response.status_code})"
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
        # Delete all records from the table using Supabase API
        response = requests.delete(
            f"{SUPABASE_URL}/rest/v1/news_searches",
            headers=supabase_headers
        )
        
        if response.status_code == 204:
            return {"status": "success", "message": "All records deleted"}
        else:
            return {"status": "error", "message": f"API returned {response.status_code}"}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}