import os
import requests
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

class NewsRequest(BaseModel):
    topic: str
    days_back: Optional[int] = 3
    max_articles: Optional[int] = 5

class NewsResponse(BaseModel):
    status: str
    summary: str
    articles_found: int
    topic: str

app = FastAPI()

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

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.post("/predict")
def predict(input_data: str):
    return {"prediction": input_data}

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
        
        return {
            "topic": topic,
            "articles_found": len(articles),
            "articles": articles
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "endpoints": {
            "GET /": "Root endpoint",
            "POST /predict": "Prediction endpoint",
            "POST /summarize-news": "News summarization",
            "GET /search-news/{topic}": "News search",
            "GET /health": "Health check"
        }
    }