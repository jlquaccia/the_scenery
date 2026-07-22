--liquibase formatted sql

--changeset jason:005-conversations
--comment Anonymous conversations (DECISIONS.md D3): UUID primary key, no user table yet.
CREATE TABLE conversations (
  id CHAR(36) PRIMARY KEY,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
--rollback DROP TABLE conversations;

--changeset jason:006-messages
--comment Message log; summary supports context compression (DESIGN.md §5).
CREATE TABLE messages (
  id INT PRIMARY KEY AUTO_INCREMENT,
  conversation_id CHAR(36) NOT NULL,
  role ENUM('user','assistant','tool') NOT NULL,
  content MEDIUMTEXT,
  summary VARCHAR(500),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_messages_conversation FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
--rollback DROP TABLE messages;
