--liquibase formatted sql

--changeset jason:001-genres
--comment Genre taxonomy (thrash metal → metal → rock); adjacency list via parent_id.
CREATE TABLE genres (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL UNIQUE,
  parent_id INT NULL,
  CONSTRAINT fk_genres_parent FOREIGN KEY (parent_id) REFERENCES genres(id)
);
--rollback DROP TABLE genres;
