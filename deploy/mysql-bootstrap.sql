-- Run with a DBA account on the existing server; replace both passwords first.
CREATE DATABASE IF NOT EXISTS agent_platform CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'agent_platform'@'%' IDENTIFIED BY 'REPLACE_PLATFORM_PASSWORD';
GRANT ALL PRIVILEGES ON agent_platform.* TO 'agent_platform'@'%';
-- Create a separate restricted business user. Grant only reviewed tables/views.
CREATE USER IF NOT EXISTS 'agent_business_ro'@'%' IDENTIFIED BY 'REPLACE_BUSINESS_PASSWORD';
-- Example only; replace database and view names:
-- GRANT SELECT ON mes.approved_production_view TO 'agent_business_ro'@'%';
-- Restrict host patterns to the application VM address before production use.
