--liquibase formatted sql

--changeset jason:002-locations
--comment Geographic hierarchy: city → metro → state → country (adjacency list).
--comment Deviations from DESIGN.md §3.3, driven by spike S3 (see spikes/NOTES.md):
--comment   * level gains 'metro' — metro regions (e.g. SF Bay Area) are OUR rows; MusicBrainz
--comment     has no metro concept, and scoring rolls up city → metro/region → country (D1).
--comment   * mb_area_id — MusicBrainz area MBID for ingestion identity/dedup (S3 finding 4).
CREATE TABLE locations (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(150) NOT NULL,
  level ENUM('city','metro','state','country') NOT NULL,
  parent_id INT NULL,
  lat DECIMAL(9,6),
  lng DECIMAL(9,6),
  mb_area_id CHAR(36) NULL,
  CONSTRAINT fk_locations_parent FOREIGN KEY (parent_id) REFERENCES locations(id),
  CONSTRAINT uq_locations_mb_area UNIQUE (mb_area_id),
  INDEX idx_level (level)
);
--rollback DROP TABLE locations;
