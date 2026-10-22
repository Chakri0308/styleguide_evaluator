import type { components } from "./api-types";

type S = components["schemas"];

export type Guide = S["GuideOut"];
export type GuideVersion = S["GuideVersionOut"];
export type IngestionStatus = S["IngestionStatus"];
export type Stage = S["StageOut"];
export type PageInfo = S["PageOut"];

export const INGEST_STAGES = ["parsing", "extracting", "chunking", "embedding", "indexing"] as const;
export type IngestStageName = (typeof INGEST_STAGES)[number];

export type StyleProfile = S["StyleProfile"];
export type ColorItem = S["ColorItem"];
export type TypographyItem = S["TypographyItem"];
export type RuleItem = S["RuleItem"];
export type ImageItem = S["ImageItem"];
export type SourceRef = S["SourceRef"];
export type FontUsage = S["FontUsage"];
export type ElementInfo = S["ElementOut"];

export const RULE_CATEGORIES = [
  ["voice_tone", "Voice & tone"],
  ["writing_rules", "Writing"],
  ["color_usage", "Color usage"],
  ["typography_usage", "Typography usage"],
  ["logo_rules", "Logo"],
  ["imagery_rules", "Imagery"],
  ["components", "Components"],
  ["spacing_grid", "Spacing & grid"],
  ["accessibility", "Accessibility"],
  ["misc_rules", "Other"],
] as const;
export type RuleCategory = (typeof RULE_CATEGORIES)[number][0];

export type Comparison = S["ComparisonOut"];
export type FindingT = S["FindingOut"];
export type CitationRefT = S["CitationRef"];
export type ComparisonListItem = S["ComparisonListItem"];

export const COMPARE_STAGES = ["aligning", "deterministic_checks", "judging", "scoring"] as const;
export const FINDING_STATUSES = ["conflict", "deviation", "missing", "new", "compliant"] as const;
export const SEVERITIES = ["critical", "major", "minor", "info"] as const;
export const FINDING_CATEGORIES: Record<string, string> = {
  colors: "Color",
  typography: "Typography",
  logo_rules: "Logo",
  imagery_rules: "Imagery",
  voice_tone: "Voice & tone",
  writing_rules: "Writing",
  accessibility: "Accessibility",
  components: "Components",
  spacing_grid: "Spacing & grid",
  misc_rules: "Other",
};
