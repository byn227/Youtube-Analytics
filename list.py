import json
import logging
from pprint import pprint

import requests
from kafka import KafkaProducer

from constants import YOUTUBE_API_KEY, PLAYLIST_ID


def fetch_page(url, parameters, page_token=None):
    params = {**parameters, 'key': YOUTUBE_API_KEY}
    if page_token:
        params['pageToken'] = page_token  
    response = requests.get(url, params=params)
    payload = json.loads(response.text)
    logging.info("Response page received")
    return payload


def fetch_page_lists(url, parameters):
    page_token = None
    while True:
        payload = fetch_page(url, parameters, page_token)
        yield from payload.get('items', [])
        page_token = payload.get('nextPageToken')  
        if page_token is None:
            break


def format_video(video):
    return {
        'title': video['snippet']['title'],
        'likes': int(video['statistics'].get('likeCount', 0)),
        'comments': int(video['statistics'].get('commentCount', 0)),
        'views': int(video['statistics'].get('viewCount', 0)),
        'favorites': int(video['statistics'].get('favoriteCount', 0)),
        'thumbnail': video['snippet']['thumbnails']['default']['url']
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    producer = KafkaProducer(
        bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        key_serializer=lambda k: k.encode('utf-8')
    )

    count = 0
    for video_item in fetch_page_lists(
        "https://www.googleapis.com/youtube/v3/playlistItems",
        {
            'part': 'snippet,contentDetails,status',
            'playlistId': PLAYLIST_ID,
            'maxResults': 50  
        }
    ):
        video_id = video_item['contentDetails']['videoId']
        for video in fetch_page_lists(
            "https://www.googleapis.com/youtube/v3/videos",
            {
                'part': 'snippet,statistics,status',
                'id': video_id,
                'maxResults': 50
            }
        ):
            data = format_video(video)
            logging.info(f"📤 Sending video: {data['title']}")
            producer.send('youtube_videos', value=data, key=video_id)
            count += 1

    producer.flush() 
