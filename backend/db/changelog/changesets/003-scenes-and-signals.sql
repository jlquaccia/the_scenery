--liquibase formatted sql

--changeset jason:003-scenes
--comment The core entity: a scene = genre × location, with a precomputed score
--comment (batch job, roadmap 1.6) so ranking queries are a single indexed lookup.
CREATE TABLE scenes (
  id INT PRIMARY KEY AUTO_INCREMENT,
  genre_id INT NOT NULL,
  location_id INT NOT NULL,
  scene_score DECIMAL(6,2) NOT NULL DEFAULT 0,
  score_updated_at TIMESTAMP NULL,
  description TEXT,
  UNIQUE KEY uq_scene (genre_id, location_id),
  CONSTRAINT fk_scenes_genre FOREIGN KEY (genre_id) REFERENCES genres(id),
  CONSTRAINT fk_scenes_location FOREIGN KEY (location_id) REFERENCES locations(id),
  INDEX idx_genre_score (genre_id, scene_score DESC)
);
--rollback DROP TABLE scenes;

--changeset jason:004-scene-signals
--comment Evidence feeding the score — keeps rankings explainable ("why #1?").
--comment Deviation from DESIGN.md §3.3 (spike S3 finding 4): mb_id carries the
--comment MusicBrainz MBID for band signals; unique per scene for ingestion dedup.
CREATE TABLE scene_signals (
  id INT PRIMARY KEY AUTO_INCREMENT,
  scene_id INT NOT NULL,
  signal_type ENUM('band','venue','festival','label','release','historic'),
  name VARCHAR(200),
  weight DECIMAL(5,2) DEFAULT 1.0,
  mb_id CHAR(36) NULL,
  metadata JSON,
  CONSTRAINT fk_signals_scene FOREIGN KEY (scene_id) REFERENCES scenes(id),
  UNIQUE KEY uq_signal_mb (scene_id, mb_id)
);
--rollback DROP TABLE scene_signals;
