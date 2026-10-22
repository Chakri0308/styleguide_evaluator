import type { components } from "./api-types";

type S = components["schemas"];

export type Guide = S["GuideOut"];
export type GuideVersion = S["GuideVersionOut"];
export type IngestionStatus = S["IngestionStatus"];
export type Stage = S["StageOut"];
export type PageInfo = S["PageOut"];

export const INGEST_STAGES = ["parsing", "extracting", "chunking", "embedding", "indexing"] as const;
export type IngestStageName = (typeof INGEST_STAGES)[number];
