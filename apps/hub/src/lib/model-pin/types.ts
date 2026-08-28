export type ModelPrice = {
  input: number;
  output: number;
};

export type PinnedModel = {
  name: string;
  description: string;
  family: string;
  lab: string;
  release_date: string;
  context: number | null;
  output: number | null;
  open_weights: boolean;
  reasoning: boolean;
  tool_call: boolean;
  attachment: boolean;
  weights: string | null;
};

export type PinnedLab = {
  name: string;
  logo: string;
};

export type ModelPin = {
  format: string;
  source: string;
  pinned_at: string;
  labs: Record<string, PinnedLab>;
  models: Record<string, PinnedModel>;
  prefixes: string[];
  lookup: Record<string, string[]>;
  prices: Record<string, Record<string, ModelPrice>>;
  aliases: Record<string, string>;
};

export type ModelJoin = {
  overlay: string;
  canonical: string | null;
  hits: string[];
};
