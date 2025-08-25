import os
import requests
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor

# Database connection function
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host="db.cyniazclgdffjcjhneau.supabase.co",
            database="postgres",
            user="postgres",
            password="Harish@Harini",
            port="5432",
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

class TopicRequest(BaseModel):
    topic: str
    days_back: int = 3  # Optional with default value

app = FastAPI()

# Your existing endpoints
@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.post("/predict")
def predict(input_data: str):
    return {"prediction": input_data}

# ======== NEW NEWS SUMMARIZATION ENDPOINTS ========

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

# Set up API keys
SERPER_API_KEY = "994cc60dc5f8832509cd540db1c3e00c6df41a99"

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
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to database")
        return False
    
    try:
        cur = conn.cursor()
        
        # Create table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS news_searches (
                id SERIAL PRIMARY KEY,
                topic VARCHAR(255) NOT NULL,
                search_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                articles_found INTEGER,
                articles JSONB
            )
        """)
        
        # Insert the search results
        cur.execute(
            "INSERT INTO news_searches (topic, articles_found, articles) VALUES (%s, %s, %s)",
            (topic, len(articles), json.dumps(articles))
        )
        
        conn.commit()
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Database error: {e}")
        if conn:
            conn.close()
        return False

# NEW ENDPOINT: News Summarization
@app.post("/summarize-news", response_model=NewsResponse)
async def summarize_news(request: NewsRequest):
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
        
        # Store results in Supabase
        store_in_supabase(request.topic, articles)
        
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
        
        # Store results in Supabase
        store_in_supabase(topic, articles)
        
        return {
            "topic": topic,
            "articles_found": len(articles),
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
        cur.execute("SELECT * FROM news_searches ORDER BY search_timestamp DESC")
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return {"history": results}
        
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# NEW ENDPOINT: Health check with news API status
@app.get("/health")
async def health_check():
    # Test database connection
    db_status = "connected" if get_db_connection() else "disconnected"
    
    return {
        "status": "healthy", 
        "database": db_status,
        "endpoints": {
            "GET /": "Root endpoint",
            "POST /predict": "Prediction endpoint",
            "POST /summarize-news": "News summarization",
            "GET /search-news/{topic}": "News search",
            "GET /search-history": "View search history",
            "GET /health": "Health check"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)