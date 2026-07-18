#!/bin/bash
# First-boot MySQL init (runs only when the data volume is empty):
# creates the two service accounts so nothing but emergencies uses root.
#   - migrator: DDL+DML on the app schema (Liquibase)
#   - app:      DML only (API); cannot CREATE/ALTER/DROP
set -euo pipefail

mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CREATE USER IF NOT EXISTS '${MYSQL_MIGRATOR_USER}'@'%' IDENTIFIED BY '${MYSQL_MIGRATOR_PASSWORD}';
GRANT CREATE, ALTER, DROP, INDEX, REFERENCES, LOCK TABLES,
      SELECT, INSERT, UPDATE, DELETE
  ON \`${MYSQL_DATABASE}\`.* TO '${MYSQL_MIGRATOR_USER}'@'%';

CREATE USER IF NOT EXISTS '${MYSQL_APP_USER}'@'%' IDENTIFIED BY '${MYSQL_APP_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE
  ON \`${MYSQL_DATABASE}\`.* TO '${MYSQL_APP_USER}'@'%';

FLUSH PRIVILEGES;
SQL

echo "Created ${MYSQL_MIGRATOR_USER} (DDL+DML) and ${MYSQL_APP_USER} (DML) for ${MYSQL_DATABASE}"
