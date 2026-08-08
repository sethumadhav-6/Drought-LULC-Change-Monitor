export interface IndexDef {
  code: string;
  name: string;
  formula: string;
  category: string;
  reference: string;
}

export interface DataSourceInfo {
  label: string;
  gee_collection: string;
  pc_collection: string;
  revisit_days: number;
  notes: string;
}

export interface AnalysisStats {
  [indexCode: string]: { pre_mean: number | null; post_mean: number | null } | Record<string, unknown>;
}

export interface DatasetRequest {
  id: string;
  requester_name: string;
  requester_email: string;
  aoi_name: string;
  data_source: string;
  indexes: string[];
  date_start: string;
  date_end: string;
  status: "requested" | "under_review" | "approved" | "rejected" | "released";
  created_at: string;
  purpose?: string | null;
}
