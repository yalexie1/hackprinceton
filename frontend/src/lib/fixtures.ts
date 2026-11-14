import house from "../../fixtures/house.json";
import office from "../../fixtures/office.json";
import sharedHouse from "../../../specs/examples/house/run_result.json";
import sharedOffice from "../../../specs/examples/office/run_result.json";
import sharedHouseEvents from "../../../specs/examples/house/run_events.json";
import sharedOfficeEvents from "../../../specs/examples/office/run_events.json";
import type {
  DocumentDraft,
  DocumentRequest,
  PropertySummary,
  RunEvent,
  RunResult,
} from "./types";
export const budgets = [5000, 15000, 30000] as const;
const sharedRuns = [sharedHouse, sharedOffice] as unknown as RunResult[];
const fixtures = [
  ...sharedRuns.map((run) => ({
    property: run.property,
    runs: { [String(run.request.budget_usd)]: run },
  })),
  house,
  office,
] as unknown as {
  property: PropertySummary;
  runs: Record<string, RunResult>;
}[];
export const demoProperties = fixtures.map((f) => f.property);
export function demoBudgets(sid?: string) {
  const fixture = fixtures.find((f) => f.property.sid === sid);
  return fixture
    ? Object.keys(fixture.runs)
        .map(Number)
        .sort((a, b) => a - b)
    : [...budgets];
}
export function demoRun(sid: string, budget: number): RunResult {
  const fixture = fixtures.find((f) => f.property.sid === sid);
  const run = fixture?.runs[String(budget)];
  if (!run)
    throw new Error(
      "Choose one of the saved demo budgets. Custom budgets are available in live mode.",
    );
  const result = structuredClone(run);
  if (!result.warnings.some((warning) => /illustrative/i.test(warning)))
    result.warnings.unshift(
      "Illustrative shared contract example; not a live building analysis.",
    );
  return result;
}
export const demoQuestion = {
  id: "demo-insulation",
  assumption_key: "wall.u_value",
  prompt: "What do you know about the wall insulation?",
  choices: [
    { label: "Insulated", value: "insulated" },
    { label: "Not sure", value: null },
  ],
  impact_note:
    "This assumption changes which envelope upgrades are worth evaluating. In this demo, answering advances the saved scenario.",
};
export const demoStages: RunEvent[] = [
  {
    type: "todo",
    stage: "plan",
    message: "Plan the audit and identify the available building layers",
    payload: {},
  },
  {
    type: "stage_done",
    stage: "ingest",
    message: "Load the saved property bundle and its provenance",
    payload: {},
  },
  {
    type: "stage_done",
    stage: "model",
    message: "Load the illustrative building model and assumption ranges",
    payload: {},
  },
  {
    type: "fallback",
    stage: "model",
    message:
      "Roof geometry is assumed in this fixture; structural suitability is unknown",
    payload: {},
  },
  {
    type: "question",
    stage: "assumptions",
    message: demoQuestion.prompt,
    payload: demoQuestion,
  },
  {
    type: "stage_done",
    stage: "baseline",
    message: "Load the saved baseline and retrofit comparison",
    payload: {},
  },
  {
    type: "stage_done",
    stage: "plan",
    message: "Load the saved budget plan with costs, savings, and evidence",
    payload: {},
  },
  {
    type: "done",
    stage: "done",
    message: "Your illustrative plan is ready to explore",
    payload: {},
  },
];
export function demoEvents(sid: string): RunEvent[] {
  const shared =
    sid === sharedHouse.property.sid
      ? sharedHouseEvents
      : sid === sharedOffice.property.sid
        ? sharedOfficeEvents
        : null;
  return structuredClone((shared || demoStages) as RunEvent[]);
}
export function fixtureSource(sid: string) {
  return sharedRuns.some((run) => run.property.sid === sid)
    ? "Shared contract example"
    : "UI sandbox · 3 budget scenarios";
}
export function demoDraft(body: DocumentRequest): DocumentDraft {
  const names: Record<string, string> = {
    retrofit_contract_residential: "Residential retrofit agreement",
    retrofit_contract_commercial: "Commercial retrofit agreement",
    solar_installation_agreement: "Solar installation agreement",
    bid_package_rfp: "Contractor bid package",
    energy_savings_guarantee: "Energy savings guarantee addendum",
    cpace_package: "Commercial C-PACE package",
  };
  const blanks = [
    "contractor_license",
    "start_date",
    "completion_date",
    "property_legal_description",
  ];
  const owner = body.fields.owner_name.trim() || "{{owner_name}}";
  const contractor =
    body.fields.contractor_name.trim() || "{{contractor_name}}";
  if (!body.fields.owner_name.trim()) blanks.push("owner_name");
  if (!body.fields.contractor_name.trim()) blanks.push("contractor_name");
  return {
    doc_id: "illustrative-draft",
    doc_type: body.doc_type,
    state: body.state,
    markdown: `# ${names[body.doc_type]}\n\nILLUSTRATIVE PREVIEW — draft for attorney review, not legal advice.\nThis preview demonstrates the document interface. It is not a verified contract template.\n\n## Parties\nOwner: ${owner}\nContractor: ${contractor}\nContractor license: {{contractor_license}}\nJurisdiction: ${body.state}\n\n## Property\n{{property_legal_description}}\n\n## Proposed scope\nSelected measures: ${body.measure_ids.join(", ")}\nPricing, specifications, and permits require confirmation.\n\n## Schedule\nStart: {{start_date}}\nCompletion: {{completion_date}}\n\n## Review before execution\nConfirm the scope, payment schedule, cancellation notices, licensing, warranties, and jurisdiction-specific terms with qualified counsel. Estimated energy savings are not a performance guarantee.`,
    unfilled_placeholders: blanks,
    statutory_checks: [
      {
        requirement: "State-specific contract terms require legal verification",
        citation: "Not verified in demo mode",
        satisfied: false,
        note: "The backend legal lane will supply the reviewed template and statutory checks.",
      },
    ],
    disclaimer:
      "Illustrative preview. Draft for attorney review, not legal advice.",
  };
}
