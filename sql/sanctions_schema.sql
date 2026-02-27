--
-- PostgreSQL database dump
--

\restrict yiAXE68RLH2N9yP6SuxCerb8WpCyNv2qNfICtYbqFR9MdmZh8mqcibsj8PcAVyc

-- Dumped from database version 16.11 (Debian 16.11-1.pgdg13+1)
-- Dumped by pg_dump version 16.11 (Debian 16.11-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: bis_dpl; Type: TABLE; Schema: public; Owner: mic_app
--

CREATE TABLE public.bis_dpl (
    id integer NOT NULL,
    name text NOT NULL,
    street_address text,
    city text,
    state text,
    country text,
    postal_code text,
    effective_date date,
    expiration_date date,
    standard_order text,
    last_update date,
    action text,
    row_hash text NOT NULL,
    source_url text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.bis_dpl OWNER TO mic_app;

--
-- Name: bis_dpl_id_seq; Type: SEQUENCE; Schema: public; Owner: mic_app
--

CREATE SEQUENCE public.bis_dpl_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.bis_dpl_id_seq OWNER TO mic_app;

--
-- Name: bis_dpl_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mic_app
--

ALTER SEQUENCE public.bis_dpl_id_seq OWNED BY public.bis_dpl.id;


--
-- Name: events; Type: TABLE; Schema: public; Owner: mic
--

CREATE TABLE public.events (
    event_id uuid NOT NULL,
    event_type text NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    actor_type text NOT NULL,
    actor_id text NOT NULL,
    correlation_id text,
    payload jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    event_hash text,
    previous_hash text
);


ALTER TABLE public.events OWNER TO mic;

--
-- Name: idempotency_keys; Type: TABLE; Schema: public; Owner: mic
--

CREATE TABLE public.idempotency_keys (
    actor_type text NOT NULL,
    actor_id text NOT NULL,
    idempotency_key text NOT NULL,
    request_hash text NOT NULL,
    response_body jsonb DEFAULT '{}'::jsonb,
    status_code integer DEFAULT 200,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    event_id uuid,
    aggregate_type text,
    aggregate_id text,
    response_created_at timestamp with time zone
);


ALTER TABLE public.idempotency_keys OWNER TO mic;

--
-- Name: ingestion_versions; Type: TABLE; Schema: public; Owner: mic
--

CREATE TABLE public.ingestion_versions (
    version_id integer NOT NULL,
    source text NOT NULL,
    content_hash text NOT NULL,
    entry_count integer NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.ingestion_versions OWNER TO mic;

--
-- Name: ingestion_versions_version_id_seq; Type: SEQUENCE; Schema: public; Owner: mic
--

CREATE SEQUENCE public.ingestion_versions_version_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ingestion_versions_version_id_seq OWNER TO mic;

--
-- Name: ingestion_versions_version_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mic
--

ALTER SEQUENCE public.ingestion_versions_version_id_seq OWNED BY public.ingestion_versions.version_id;


--
-- Name: ofac_consolidated; Type: TABLE; Schema: public; Owner: mic
--

CREATE TABLE public.ofac_consolidated (
    uid text NOT NULL,
    last_name text,
    first_name text,
    entity_type text,
    programs text[],
    raw jsonb,
    ingested_at timestamp with time zone
);


ALTER TABLE public.ofac_consolidated OWNER TO mic;

--
-- Name: ofac_sdn; Type: TABLE; Schema: public; Owner: mic
--

CREATE TABLE public.ofac_sdn (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    uid text NOT NULL,
    last_name text,
    first_name text,
    entity_type text,
    programs text[],
    raw jsonb,
    ingested_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.ofac_sdn OWNER TO mic;

--
-- Name: bis_dpl id; Type: DEFAULT; Schema: public; Owner: mic_app
--

ALTER TABLE ONLY public.bis_dpl ALTER COLUMN id SET DEFAULT nextval('public.bis_dpl_id_seq'::regclass);


--
-- Name: ingestion_versions version_id; Type: DEFAULT; Schema: public; Owner: mic
--

ALTER TABLE ONLY public.ingestion_versions ALTER COLUMN version_id SET DEFAULT nextval('public.ingestion_versions_version_id_seq'::regclass);


--
-- Name: bis_dpl bis_dpl_pkey; Type: CONSTRAINT; Schema: public; Owner: mic_app
--

ALTER TABLE ONLY public.bis_dpl
    ADD CONSTRAINT bis_dpl_pkey PRIMARY KEY (id);


--
-- Name: bis_dpl bis_dpl_row_hash_key; Type: CONSTRAINT; Schema: public; Owner: mic_app
--

ALTER TABLE ONLY public.bis_dpl
    ADD CONSTRAINT bis_dpl_row_hash_key UNIQUE (row_hash);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: public; Owner: mic
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (event_id);


--
-- Name: idempotency_keys idempotency_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: mic
--

ALTER TABLE ONLY public.idempotency_keys
    ADD CONSTRAINT idempotency_keys_pkey PRIMARY KEY (actor_type, actor_id, idempotency_key);


--
-- Name: ingestion_versions ingestion_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: mic
--

ALTER TABLE ONLY public.ingestion_versions
    ADD CONSTRAINT ingestion_versions_pkey PRIMARY KEY (version_id);


--
-- Name: ofac_consolidated ofac_consolidated_pkey; Type: CONSTRAINT; Schema: public; Owner: mic
--

ALTER TABLE ONLY public.ofac_consolidated
    ADD CONSTRAINT ofac_consolidated_pkey PRIMARY KEY (uid);


--
-- Name: ofac_sdn ofac_sdn_pkey; Type: CONSTRAINT; Schema: public; Owner: mic
--

ALTER TABLE ONLY public.ofac_sdn
    ADD CONSTRAINT ofac_sdn_pkey PRIMARY KEY (id);


--
-- Name: ofac_sdn ofac_sdn_uid_key; Type: CONSTRAINT; Schema: public; Owner: mic
--

ALTER TABLE ONLY public.ofac_sdn
    ADD CONSTRAINT ofac_sdn_uid_key UNIQUE (uid);


--
-- Name: idx_bis_dpl_country; Type: INDEX; Schema: public; Owner: mic_app
--

CREATE INDEX idx_bis_dpl_country ON public.bis_dpl USING btree (country);


--
-- Name: idx_bis_dpl_name; Type: INDEX; Schema: public; Owner: mic_app
--

CREATE INDEX idx_bis_dpl_name ON public.bis_dpl USING btree (name);


--
-- Name: ix_events_aggregate; Type: INDEX; Schema: public; Owner: mic
--

CREATE INDEX ix_events_aggregate ON public.events USING btree (aggregate_type, aggregate_id, created_at, event_id);


--
-- Name: ux_idempotency_keys_actor_key; Type: INDEX; Schema: public; Owner: mic
--

CREATE UNIQUE INDEX ux_idempotency_keys_actor_key ON public.idempotency_keys USING btree (actor_type, actor_id, idempotency_key);


--
-- Name: TABLE events; Type: ACL; Schema: public; Owner: mic
--

GRANT SELECT,INSERT ON TABLE public.events TO mic_app;


--
-- Name: TABLE idempotency_keys; Type: ACL; Schema: public; Owner: mic
--

GRANT SELECT,INSERT,UPDATE ON TABLE public.idempotency_keys TO mic_app;


--
-- Name: TABLE ingestion_versions; Type: ACL; Schema: public; Owner: mic
--

GRANT ALL ON TABLE public.ingestion_versions TO mic_app;


--
-- Name: SEQUENCE ingestion_versions_version_id_seq; Type: ACL; Schema: public; Owner: mic
--

GRANT SELECT,USAGE ON SEQUENCE public.ingestion_versions_version_id_seq TO mic_app;


--
-- Name: TABLE ofac_consolidated; Type: ACL; Schema: public; Owner: mic
--

GRANT ALL ON TABLE public.ofac_consolidated TO mic_app;


--
-- Name: TABLE ofac_sdn; Type: ACL; Schema: public; Owner: mic
--

GRANT ALL ON TABLE public.ofac_sdn TO mic_app;


--
-- PostgreSQL database dump complete
--

\unrestrict yiAXE68RLH2N9yP6SuxCerb8WpCyNv2qNfICtYbqFR9MdmZh8mqcibsj8PcAVyc

