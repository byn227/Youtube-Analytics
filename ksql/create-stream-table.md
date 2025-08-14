CREATE STREAM youtube_videos(
    video_id varchar-key,
    title varchar,
    likes integer,
    views integer,
    favorites integer,
    thumbnail varchar,
) with (kafka_topic=’youtube_videos’, partitions=1,
value_format=’json’);


Create table youtube_analytics_changes with (kafka_topic=‘youtube_analytics_changes’) as
select # ksqlDB: Streams and Tables for YouTube Analytics

 This document defines the ksqlDB artifacts used to ingest YouTube video snapshots, compute changes, and deliver formatted Slack notifications.

 Notes:
 - Always use straight quotes ' and avoid curly quotes.
 - Avoid trailing commas in column lists.
 - For replays, set `SET 'auto.offset.reset'='earliest';`. For only new data, use `latest`.

 ## 1) Source stream: `youtube_videos`
 ```sql
 CREATE STREAM youtube_videos (
   video_id  VARCHAR KEY,
   title     VARCHAR,
   likes     INT,
   views     INT,
   favorites INT,
   thumbnail VARCHAR
 ) WITH (
   kafka_topic='youtube_videos',
   partitions=1,
   value_format='json'
 );
 ```

 ## 2) Aggregation table: last two measurements per video
 ```sql
 CREATE TABLE youtube_analytics_changes
 WITH (kafka_topic='youtube_analytics_changes') AS
 SELECT
   video_id,
   LATEST_BY_OFFSET(title)            AS title,
   LATEST_BY_OFFSET(views, 2)[1]      AS views_prev,
   LATEST_BY_OFFSET(views, 2)[2]      AS views_curr,
   LATEST_BY_OFFSET(likes, 2)[1]      AS likes_prev,
   LATEST_BY_OFFSET(likes, 2)[2]      AS likes_curr,
   LATEST_BY_OFFSET(favorites, 2)[1]  AS favorites_prev,
   LATEST_BY_OFFSET(favorites, 2)[2]  AS favorites_curr
 FROM youtube_videos
 GROUP BY video_id
 EMIT CHANGES;
 ```

 ## 3) Base stream over the table's changelog topic
 If not already present, create a stream that reads the changelog topic from the table above.

 ```sql
 CREATE STREAM youtube_analytics_change_stream_base (
   video_id        VARCHAR KEY,
   title           VARCHAR,
   views_prev      INT,
   views_curr      INT,
   likes_prev      INT,
   likes_curr      INT,
   favorites_prev  INT,
   favorites_curr  INT
 ) WITH (
   kafka_topic='youtube_analytics_changes',
   value_format='json'
 );
 ```

 ## 4) Derived stream: keep key, include title in text, filter by ≥ 5000 view change
 ```sql
 CREATE STREAM youtube_analytics_change_stream
 WITH (
   kafka_topic='youtube_analytics_change_stream',
   value_format='json',
   partitions=1
 ) AS
 SELECT
   video_id,
   CONCAT(
     'Video ', CAST(video_id AS STRING), ' | ',
     title, ' | views: ', CAST(views_prev AS STRING), ' -> ', CAST(views_curr AS STRING),
     ' | likes: ', CAST(likes_prev AS STRING), ' -> ', CAST(likes_curr AS STRING),
     ' | favorites: ', CAST(favorites_prev AS STRING), ' -> ', CAST(favorites_curr AS STRING)
   ) AS text
 FROM youtube_analytics_change_stream_base
 WHERE ABS(views_curr - views_prev) >= 5000
 EMIT CHANGES;
 ```

 ## 5) Slack sink stream (Avro): key = `video_id`, value field = `TEXT`
 ```sql
 CREATE STREAM slack_output (
   video_id VARCHAR KEY,
   TEXT     VARCHAR
 ) WITH (
   kafka_topic='slack_output',
   partitions=1,
   value_format='avro'
 );
 ```

 ## 6) Route filtered messages to the Slack sink
 ```sql
 INSERT INTO slack_output
 SELECT
   video_id,
   text AS TEXT
 FROM youtube_analytics_change_stream;
 ```

 ## 7) Kafka Connect HTTP Sink (Slack) – example configuration
 The connector should read from topic `slack_output` and rename the Avro field `TEXT` to the JSON field `text` expected by Slack. The body will be posted as `{ "text": "..." }`.

 ```json
 {
   "name": "slack_",
   "connector.class": "io.confluent.connect.http.HttpSinkConnector",
   "tasks.max": "1",
   "topics": "slack_output",
   "request.method": "post",
   "http.api.url": "https://hooks.slack.com/services/XXX/YYY/ZZZ",
   "headers": "content-type:application/json",
   "request.body.format": "json",
   "batch.max.size": "1",
   "batch.json.as.array": "false",
   "reporter.bootstrap.servers": "broker:29092",
   "reporter.result.topic.replication.factor": "1",
   "reporter.error.topic.replication.factor": "1",
   "transforms": "rename",
   "transforms.rename.type": "org.apache.kafka.connect.transforms.ReplaceField$Value",
   "transforms.rename.renames": "TEXT:text"
 }
 ```

 Summary:
 - `video_id` remains the key throughout.
 - The Slack message text includes the video title and metrics.
 - Only messages with an absolute view change of at least 5,000 are forwarded to Slack.
   