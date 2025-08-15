
# ksqlDB: Flux et Tables pour l'analytique YouTube

Ce document décrit les artefacts ksqlDB utilisés pour ingérer des instantanés des vidéos YouTube, calculer les changements, et produire des messages formatés vers Slack.

Notes:
- Utilisez toujours des apostrophes droites ' et évitez les guillemets typographiques.
- Évitez les virgules finales dans les listes de colonnes.
- Pour rejouer l'historique: `SET 'auto.offset.reset'='earliest';`. Pour ne traiter que les nouveaux messages: `latest`.

## 1) Stream source: `youtube_videos`
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

## 2) Table d'agrégation: deux dernières mesures par vidéo
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

## 3) Stream de base sur le changelog de la table
S'il n'existe pas déjà, créer un stream lisant le topic changelog de la table ci-dessus.

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

## 4) Stream dérivé: garder la clé, inclure le titre dans le texte, filtrer par changement de vues ≥ 5000
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

## 5) Stream sink Slack (Avro): clé = `video_id`, champ de valeur = `TEXT`
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

## 6) Router les messages filtrés vers le sink Slack
```sql
INSERT INTO slack_output
SELECT
  video_id,
  text AS TEXT
FROM youtube_analytics_change_stream;
```

## 7) Kafka Connect HTTP Sink (Slack) – exemple de configuration
Le connecteur doit lire depuis `slack_output` et renommer le champ Avro `TEXT` en champ JSON `text` attendu par Slack. Le corps envoyé sera `{ "text": "..." }`.

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
##Flow

![alt text](/assets/flow.png)