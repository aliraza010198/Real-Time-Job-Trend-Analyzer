# Install required packages
!pip install flask beautifulsoup4 requests pandas plotly pyngrok --quiet

# Import libraries
from flask import Flask, render_template, request
from bs4 import BeautifulSoup
import requests
import pandas as pd
import plotly.express as px
from collections import Counter
import time
from pyngrok import ngrok
import threading
import os
import re
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)

# Configuration
DATA_PATH = "jobs.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Kill any existing processes
!pkill -f flask
!pkill -f ngrok
time.sleep(2)

# Scraping Functions
def scrape_glassdoor(keyword="data analyst", max_pages=1):
    jobs = []
    try:
        for page in range(max_pages):
            url = f"https://www.glassdoor.com/Job/jobs.htm?suggestCount=0&suggestChosen=false&clickSource=searchBtn&typedKeyword={keyword.replace(' ', '+')}&sc.keyword={keyword.replace(' ', '+')}&locT=N&locId=1&jobType="
            response = requests.get(url, headers=HEADERS, timeout=10)
            time.sleep(3)  # Glassdoor is sensitive to scraping
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for card in soup.find_all('li', class_='react-job-listing'):
                try:
                    title = card.find('a', class_='jobLink').get_text(strip=True)
                    company = card.find('div', class_='d-flex').get_text(strip=True)
                    location = card.find('span', class_='loc').get_text(strip=True)
                    
                    # Extract date (Glassdoor format varies)
                    date_text = card.find('div', class_='job-age').get_text(strip=True) if card.find('div', class_='job-age') else "Recent"
                    date = parse_relative_date(date_text)
                    
                    jobs.append({
                        'title': title,
                        'company': company,
                        'location': location,
                        'skills': 'Not specified',  # Glassdoor requires login for full details
                        'date_posted': date,
                        'source': 'Glassdoor'
                    })
                except Exception as e:
                    continue
    except Exception as e:
        print(f"Glassdoor scraping error: {e}")
    return jobs

def scrape_monster(keyword="data analyst", max_pages=1):
    jobs = []
    try:
        url = f"https://www.monster.com/jobs/search/?q={keyword.replace(' ', '-')}&where=remote"
        response = requests.get(url, headers=HEADERS, timeout=10)
        time.sleep(2)  # Polite delay
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for card in soup.find_all('div', class_='card-content'):
            try:
                title = card.find('h2', class_='title').get_text(strip=True)
                company = card.find('div', class_='company').get_text(strip=True)
                location = card.find('div', class_='location').get_text(strip=True)
                
                # Extract date (Monster format)
                date_text = card.find('time').get_text(strip=True) if card.find('time') else "Recent"
                date = parse_relative_date(date_text)
                
                # Extract skills from description
                description = card.find('div', class_='description').get_text().lower() if card.find('div', class_='description') else ""
                skills = []
                for skill in ['python', 'sql', 'excel', 'tableau', 'power bi', 'r', 'machine learning']:
                    if skill in description:
                        skills.append(skill)
                
                jobs.append({
                    'title': title,
                    'company': company,
                    'location': location,
                    'skills': ', '.join(skills) if skills else 'Not specified',
                    'date_posted': date,
                    'source': 'Monster'
                })
            except Exception as e:
                continue
    except Exception as e:
        print(f"Monster scraping error: {e}")
    return jobs

def parse_relative_date(date_text):
    """Convert relative dates (e.g. '2 days ago') to YYYY-MM-DD format"""
    today = datetime.today()
    
    if 'today' in date_text.lower() or 'just' in date_text.lower():
        return today.strftime('%Y-%m-%d')
    elif 'day' in date_text.lower():
        days = int(re.search(r'\d+', date_text).group())
        return (today - timedelta(days=days)).strftime('%Y-%m-%d')
    elif 'week' in date_text.lower():
        weeks = int(re.search(r'\d+', date_text).group())
        return (today - timedelta(weeks=weeks)).strftime('%Y-%m-%d')
    else:
        return date_text  # Return as-is if we can't parse

def refresh_data(keyword="data analyst"):
    jobs = scrape_glassdoor(keyword) + scrape_monster(keyword)
    if jobs:
        pd.DataFrame(jobs).to_csv(DATA_PATH, index=False)
    return jobs

def load_data():
    if os.path.exists(DATA_PATH):
        return pd.read_csv(DATA_PATH)
    return pd.DataFrame(columns=["title", "company", "location", "skills", "date_posted", "source"])

def generate_plots(df):
    plots = {}
    
    # Top skills plot
    skills = df['skills'].str.split(', ').explode()
    top_skills = skills[skills != 'Not specified'].value_counts().head(10)
    plots['skills'] = px.bar(top_skills, title='Top 10 Required Skills', labels={'value': 'Count', 'index': 'Skill'})
    
    # Job trends plot
    if 'date_posted' in df.columns:
        trends = df.groupby(pd.to_datetime(df['date_posted'])).size()
        plots['trends'] = px.line(trends, title='Job Posting Trends', labels={'value': 'Number of Jobs', 'index': 'Date'})
    
    return plots

# Flask Routes
@app.route("/", methods=["GET", "POST"])
def index():
    keyword = request.form.get("keyword", "data analyst")
    refresh = request.form.get("refresh", False)
    
    if refresh:
        jobs = refresh_data(keyword)
    else:
        jobs = load_data()
    
    if isinstance(jobs, pd.DataFrame):
        jobs = jobs.to_dict('records')
    
    df = pd.DataFrame(jobs)
    total_jobs = len(df)
    
    # Generate statistics
    top_titles = Counter(df['title']).most_common(5) if total_jobs > 0 else []
    top_locations = Counter(df['location']).most_common(5) if total_jobs > 0 else []
    plots = generate_plots(df) if total_jobs > 0 else {}
    
    return render_template('index.html',
                         jobs=jobs[:100],
                         keyword=keyword,
                         total_jobs=total_jobs,
                         top_titles=top_titles,
                         top_locations=top_locations,
                         plots=plots)

# HTML Template (would be in templates/index.html)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Job Trend Analyzer</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .search-box { margin: 20px 0; padding: 15px; background: #f5f5f5; }
        .stats { display: flex; flex-wrap: wrap; gap: 20px; margin: 20px 0; }
        .stat-card { flex: 1; min-width: 200px; padding: 15px; background: #fff; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .job-list { margin-top: 20px; }
        .job-card { padding: 15px; margin-bottom: 10px; background: #fff; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .plot { margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Job Trend Analyzer (Glassdoor & Monster)</h1>
        
        <div class="search-box">
            <form method="POST">
                <input type="text" name="keyword" placeholder="Enter job title (e.g. Data Analyst)" value="{{ keyword }}" style="padding: 8px; width: 300px;">
                <button type="submit" style="padding: 8px 15px;">Search</button>
                <button type="submit" name="refresh" value="true" style="padding: 8px 15px; margin-left: 10px;">Refresh Data</button>
            </form>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <h3>Total Jobs</h3>
                <p>{{ total_jobs }}</p>
            </div>
            <div class="stat-card">
                <h3>Top Job Titles</h3>
                <ul>
                    {% for title, count in top_titles %}
                    <li>{{ title }} ({{ count }})</li>
                    {% endfor %}
                </ul>
            </div>
            <div class="stat-card">
                <h3>Top Locations</h3>
                <ul>
                    {% for loc, count in top_locations %}
                    <li>{{ loc }} ({{ count }})</li>
                    {% endfor %}
                </ul>
            </div>
        </div>
        
        {% if plots %}
        <div class="plot">
            {{ plots.skills.to_html(full_html=False) | safe }}
        </div>
        <div class="plot">
            {{ plots.trends.to_html(full_html=False) | safe }}
        </div>
        {% endif %}
        
        <div class="job-list">
            <h2>Recent Job Listings ({{ total_jobs }} total)</h2>
            {% for job in jobs %}
            <div class="job-card">
                <h3>{{ job.title }}</h3>
                <p><strong>{{ job.company }}</strong> | {{ job.location }} | {{ job.source }}</p>
                <p>Skills: {{ job.skills }}</p>
                <small>Posted: {{ job.date_posted }}</small>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

# Create template directory and file
os.makedirs('templates', exist_ok=True)
with open('templates/index.html', 'w') as f:
    f.write(HTML_TEMPLATE)

# Run Flask in a separate thread
def run_flask():
    app.run(host='0.0.0.0', port=5001)

flask_thread = threading.Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# Setup ngrok
ngrok.set_auth_token("2xYs3aOZ84A5EtCk2cPMMCpVZBT_4ZujRf7nAYZDpXGUZAdXA")
public_url = ngrok.connect(5001).public_url
print(f" * Running on {public_url}")
print(" * Press CTRL+C to quit")

# Keep the cell running
while True:
    time.sleep(1)


# Convert SAMPLE_JOBS to DataFrame and save to CSV
df = pd.DataFrame(SAMPLE_JOBS)
df.to_csv("sample_jobs.csv", index=False)
print("✅ CSV file 'sample_jobs.csv' created successfully.")
