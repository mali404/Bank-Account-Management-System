-- AgentBank-Sec core database bootstrap (SPEC §5.1, §15).
-- Runs once on first container start. Creates one schema per bank plus the
-- switch and sim-mail schemas, and enables pgvector for the RAG KB (bank-c).
-- Table definitions arrive with the bank cores in milestone M2.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS bank_a;
CREATE SCHEMA IF NOT EXISTS bank_b;
CREATE SCHEMA IF NOT EXISTS bank_c;
CREATE SCHEMA IF NOT EXISTS switch;
CREATE SCHEMA IF NOT EXISTS sim_mail;
