import os
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from textblob import TextBlob
from urllib.parse import urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
YT_API_KEY = os.getenv('YT_API_KEY')
print("YT_API_KEY loaded:", YT_API_KEY)
MAX_COMMENTS = 100

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[^\w\s]', ' ', text.lower())
    return ' '.join(text.split())

def analyze_sentiment(text):
    analysis = TextBlob(text)
    polarity = analysis.sentiment.polarity
    return {
        'polarity': round(polarity, 4),
        'subjectivity': round(analysis.sentiment.subjectivity, 4),
        'sentiment': 'positive' if polarity > 0.1 else 'negative' if polarity < -0.1 else 'neutral'
    }

def extract_video_id(url):
    clean_url = url.split('&')[0]
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{11})',
        r'(?:embed/|v/|watch\?v=)([\w-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, clean_url)
        if match:
            return match.group(1)
    return None

def get_video_details(video_id):
    try:
        from pytube import YouTube
        yt = YouTube(f'https://youtube.com/watch?v={video_id}')
        return {
            'title': yt.title,
            'thumbnail': yt.thumbnail_url,
            'author': yt.author
        }
    except:
        try:
            url = f'https://www.youtube.com/watch?v={video_id}'
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.find('meta', property='og:title')['content']
            thumbnail = soup.find('meta', property='og:image')['content']
            return {
                'title': title,
                'thumbnail': thumbnail,
                'author': 'Unknown'
            }
        except:
            return None

def get_comments(video_id, max_comments):
    comments = []
    
    if YT_API_KEY:
        try:
            from googleapiclient.discovery import build
            youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
            results = youtube.commentThreads().list(
                part='snippet',
                videoId=video_id,
                maxResults=min(max_comments, 100),
                textFormat='plainText',
                order='relevance'
            ).execute()
            
            for item in results['items']:
                comment = item['snippet']['topLevelComment']['snippet']
                comments.append({
                    'text': comment['textDisplay'],
                    'author': comment['authorDisplayName'],
                    'likes': comment['likeCount'],
                    'published': comment['publishedAt']
                })
                if len(comments) >= max_comments:
                    break
            return comments
        except:
            pass
    
    try:
        url = f'https://www.youtube.com/watch?v={video_id}'
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        comment_elements = soup.select('yt-formatted-string#content-text')
        for element in comment_elements[:max_comments]:
            comments.append({
                'text': element.get_text(strip=True),
                'author': 'Unknown',
                'likes': 0,
                'published': ''
            })
        return comments
    except Exception as e:
        print("YouTube API error:", e)
        return []

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'Missing YouTube URL'}), 400
    
    url = data['url'].strip()
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    max_comments = min(int(data.get('max_comments', MAX_COMMENTS)), 200)
    
    video_details = get_video_details(video_id)
    if not video_details:
        return jsonify({'error': 'Could not fetch video details'}), 400
    
    raw_comments = get_comments(video_id, max_comments)
    if not raw_comments:
        return jsonify({'error': 'No comments found or comments disabled'}), 404
    
    processed_comments = []
    for comment in raw_comments:
        cleaned = clean_text(comment['text'])
        sentiment = analyze_sentiment(cleaned)
        processed_comments.append({
            **comment,
            'sentiment': sentiment['sentiment'],
            'polarity': sentiment['polarity'],
            'subjectivity': sentiment['subjectivity']
        })
    
    # Calculate statistics
    total = len(processed_comments)
    positive = sum(1 for c in processed_comments if c['sentiment'] == 'positive')
    negative = sum(1 for c in processed_comments if c['sentiment'] == 'negative')
    neutral = sum(1 for c in processed_comments if c['sentiment'] == 'neutral')
    avg_polarity = round(sum(c['polarity'] for c in processed_comments) / total, 4)
    avg_subjectivity = round(sum(c['subjectivity'] for c in processed_comments) / total, 4)

    stats = {
        'total': total,
        'positive': positive,
        'negative': negative,
        'neutral': neutral,
        'avg_polarity': avg_polarity,
        'avg_subjectivity': avg_subjectivity
    }
    
    return jsonify({
        'video': {
            'id': video_id,
            'title': video_details['title'],
            'thumbnail': video_details['thumbnail'],
            'author': video_details['author']
        },
        'comments': processed_comments,
        'statistics': stats
    })

@app.route('/routes')
def list_routes():
    import urllib
    output = []
    for rule in app.url_map.iter_rules():
        methods = ','.join(sorted(rule.methods))
        url = urllib.parse.unquote(str(rule))
        output.append(f"{url} [{methods}]")
    return '<br>'.join(sorted(output))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
