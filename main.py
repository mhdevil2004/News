import os
import requests
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
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

# Database connection function - SIMPLIFIED FOR SUPABASE
def get_db_connection():
    try:
        # Use direct Supabase connection (more reliable)
        db_host = os.getenv("DB_HOST", "db.cyniazclgdffjcjhneau.supabase.co")
        db_name = os.getenv("DB_NAME", "postgres")
        db_user = os.getenv("DB_USER", "postgres")
        db_password = os.getenv("DB_PASSWORD", "Harish@Harini")
        db_port = os.getenv("DB_PORT", "5432")  # Standard PostgreSQL port
        
        print(f"Connecting to Supabase: {db_host} with user: {db_user}")
        
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password,
            port=db_port,
            sslmode="require",  # SSL is REQUIRED for Supabase
            cursor_factory=RealDictCursor
        )
        
        print("Database connection successful!")
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

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
    """Store search results in Supabase database"""
    print(f"Attempting to store {len(articles)} articles for topic: {topic}")
    
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to database")
        return False
    
    try:
        cur = conn.cursor()
        
        # Create table if it doesn't exist (with error handling)
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS news_searches (
                    id SERIAL PRIMARY KEY,
                    topic VARCHAR(255) NOT NULL,
                    search_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    articles_found INTEGER,
                    articles JSONB
                )
            """)
            conn.commit()
            print("Table created or already exists")
        except Exception as e:
            print(f"Table creation warning: {e}")
            conn.rollback()
        
        # Insert the search results
        cur.execute(
            "INSERT INTO news_searches (topic, articles_found, articles) VALUES (%s, %s, %s)",
            (topic, len(articles), json.dumps(articles))
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"Successfully stored {len(articles)} articles in database!")
        return True
        
    except Exception as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()
            conn.close()
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
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM news_searches ORDER BY search_timestamp DESC LIMIT 20")
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return {"history": results}
        
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# NEW ENDPOINT: Debug database connection
@app.get("/debug-db")
async def debug_db():
    """Check database connection status"""
    try:
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT NOW() as current_time, version() as db_version")
                result = cur.fetchone()
                cur.close()
                conn.close()
                return {
                    "status": "connected", 
                    "database_time": result["current_time"],
                    "version": result["db_version"]
                }
            except Exception as e:
                return {"status": "connected but query failed", "error": str(e)}
        else:
            return {"status": "disconnected", "error": "Failed to connect to database"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# NEW ENDPOINT: Health check with news API status
@app.get("/health")
async def health_check():
    # Test database connection
    db_conn = get_db_connection()
    db_status = "connected" if db_conn else "disconnected"
    if db_conn:
        db_conn.close()
    
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
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM news_searches")
        conn.commit()
        cur.close()
        conn.close()
        
        return {"status": "success", "message": "Search history cleared"}
        
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")