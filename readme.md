# YouTube Analytics Pipeline

Stream YouTube video metrics into Kafka and process them with ksqlDB, with optional delivery to Slack via Kafka Connect HTTP Sink.

## Overview
* __Producers__: Python scripts (`list.py`, `youtubeanalytic.py`) fetch video stats from the YouTube Data API and publish to Kafka topic `youtube_videos`.
* __Kafka Stack__: Zookeeper, Kafka Broker, Schema Registry, Kafka Connect, ksqlDB Server, and Confluent Control Center are defined in `docker-compose.yaml`.
* __Stream Processing__: ksqlDB streams/tables defined in `ksql/create-stream-table.md` compute metric deltas and format messages.
* __Sinks__: Example Slack HTTP sink via Kafka Connect reads from `slack_output`.

## Repository Structure
* `docker-compose.yaml` – Confluent Platform services.
* `constants.py` – Reads API/config values from `config/config.local`.
* `list.py` – Publishes playlist videos’ metrics to Kafka (`youtube_videos`).
* `youtubeanalytic.py` – Publishes a single video’s metrics to Kafka.
* `ksql/create-stream-table.md` – ksqlDB SQL to create streams/tables and example Slack sink config.
* `connectors/` – Custom/Kafka Connect plugins mount point.
* `requirement.txt` – Python dependencies.

## Prerequisites
* Docker and Docker Compose
* Python 3.10+
* A YouTube Data API key

## Configuration
Create `config/config.local` with your API key and IDs:

```ini
[youtube]
API_KEY = <YOUR_YOUTUBE_API_KEY>
PLAYLIST_ID = <OPTIONAL_PLAYLIST_ID>
VIDEO_ID = <OPTIONAL_VIDEO_ID>
```

`constants.py` loads these values to be used by the producers.

## Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirement.txt
```

## Start the Kafka stack

```bash
docker compose up -d
```

Services (default ports):
* __Kafka Broker__: 9092 (host), 29092 (internal)
* __Zookeeper__: 2181
* __Schema Registry__: 8081
* __Kafka Connect__: 8083
* __ksqlDB Server__: 8088
* __Control Center__: 9021 (UI at http://localhost:9021)

Wait for health checks to pass (a minute or two). You can verify via Control Center.

## ksqlDB: Create streams and tables
Use the SQL in `ksql/create-stream-table.md`. Notes:
* __Use straight quotes__ `'` in SQL (avoid curly quotes copied from docs).
* Ensure the source topic `youtube_videos` exists (the producers will create it by sending messages).

Common flow defined in the doc:
* `youtube_videos` stream (JSON)
* `youtube_analytics_changes` table (latest two measurements per video)
* `youtube_analytics_change_stream_base` stream (over the table changelog)
* `youtube_analytics_change_stream` derived stream with formatted text and filters
* `slack_output` stream (Avro) for the Slack sink

## Run the producers
With the stack up and `config/config.local` set:

- __Publish a single video’s metrics__

  ```bash
  python youtubeanalytic.py
  ```

- __Publish metrics for all items in a playlist__

  ```bash
  python list.py
  ```

Both scripts send JSON messages to Kafka topic `youtube_videos` with key = `video_id` (in `list.py`).

## Optional: Slack HTTP Sink via Kafka Connect
An example connector config is included at the bottom of `ksql/create-stream-table.md`. Post it to Kafka Connect once topics/streams exist and you have a Slack webhook URL:

```bash
curl -X PUT \
  -H 'Content-Type: application/json' \
  --data @connector.json \
  http://localhost:8083/connectors/slack_/config
```

Where `connector.json` matches the example (update `http.api.url`). Ensure the connector reads from `slack_output` and uses a transform to rename `TEXT` -> `text`.

## Topics
* `youtube_videos` – input from producers (JSON)
* `youtube_analytics_changes` – table changelog (JSON)
* `youtube_analytics_change_stream` – filtered/pretty text (JSON)
* `slack_output` – final sink (Avro)




