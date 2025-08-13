import json
import logging
from pprint import pprint

import requests
from kafka import KafkaProducer

from constants import YOUTUBE_API_KEY, VIDEO_ID
if __name__ == "__main__":
    producer=KafkaProducer(bootstrap_servers='localhost:9092')
    response=requests.get("https://www.googleapis.com/youtube/v3/videos",
    { 'key': YOUTUBE_API_KEY, 
     'part': 'snippet,statistics,status', 
     'id': VIDEO_ID })
    items = json.loads(response.text).get('items', [])
    for video in items:
        video_res = {
            'title': video['snippet']['title'],
            'likes': int(video['statistics'].get('likeCount', 0)),
            'comments': int(video['statistics'].get('commentCount', 0)),
            'views': int(video['statistics'].get('viewCount', 0)),
            'favorites': int(video['statistics'].get('favoriteCount', 0)),
            'thumbnail': video['snippet']['thumbnails']['default']['url']
        }

        pprint(video_res)
        producer.send('youtube_videos', json.dumps(video_res).encode('utf-8'))
        producer.flush()