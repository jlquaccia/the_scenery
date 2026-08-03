--liquibase formatted sql

--changeset jason:011-signal-type-artist
--comment Roadmap 1.11 / DECISIONS.md D1 amendment — solo artists count as signals.
--comment Genres built on producers rather than bands (techno, hip hop) were invisible
--comment to a Group-only rule. 'artist' stays distinct from 'band' so the two remain
--comment separable if they are ever weighted differently.
ALTER TABLE scene_signals
  MODIFY signal_type ENUM('band','artist','venue','festival','label','release','historic') NULL;
--rollback ALTER TABLE scene_signals
--rollback   MODIFY signal_type ENUM('band','venue','festival','label','release','historic') NULL;
