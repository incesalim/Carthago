"use client";

export type Navigation = {
  sections: { number: number; title: string; page_start: number; page_end: number }[];
  contents_entries: { id: string; section: number; number: number; title: string;
    declared_folio: string | null; page_start: number | null; page_end: number | null;
    mapping_status: string; end_mapping_status: string;
    source_lines: { page: number; text: string }[];
    folio_sources: { page: number }[];
    body_title_matches: { page: number; kind: string }[] }[];
  issues: { kind: string; entry_id?: string; body_section_page?: number }[];
};

export default function DocumentNavigationPreview({ navigation, onPage }: {
  navigation?: Navigation; onPage: (page: number) => void;
}) {
  if (!navigation) return null;
  const jump = (page: number, label: string) => <button className="text-primary hover:underline" onClick={() => onPage(page)}>{label}</button>;
  return <details className="mb-4 border-y border-border py-3 text-xs">
    <summary className="cursor-pointer font-semibold">Report sections and printed contents</summary>
    <p className="my-3 text-muted-foreground">Section links follow banners in the report. Printed contents references are retained separately; matching a page number does not confirm that the named content starts there.</p>
    {navigation.sections.length === 0 && <p className="my-2 text-warning">Section boundaries could not be resolved from the body banners.</p>}
    {navigation.sections.map((section) => <div key={section.number} className="border-t border-hair py-3">
      <p className="font-semibold">{jump(section.page_start, `${section.number}. ${section.title}`)} <span className="font-normal text-muted-foreground">· PDF pages {section.page_start}–{section.page_end}</span></p>
    </div>)}
    <h4 className="mt-3 font-semibold">Printed contents · {navigation.contents_entries.length} entries</h4>
    <ol className="divide-y divide-hair">
      {navigation.contents_entries.map((entry) => {
        const issues = navigation.issues.filter((issue) => issue.entry_id === entry.id);
        const conflict = issues.some((issue) => issue.kind.startsWith("contents_target_"));
        const bodySectionPage = issues.find((issue) => issue.body_section_page != null)?.body_section_page;
        return <li key={entry.id} className="py-3">
          <p>{entry.section}.{entry.number} · {entry.title}</p>
          <p className="mt-1 text-muted-foreground">Printed page reference: <span className="font-mono">{entry.declared_folio ?? "unread"}</span>{" · "}
            {entry.page_start != null ? jump(entry.page_start, `Printed folio found on PDF page ${entry.page_start}`)
              : entry.mapping_status === "ambiguous" ? <>More than one matching PDF page: {entry.folio_sources.map((s, i) => <span key={i}>{i > 0 && ", "}{jump(s.page, String(s.page))}</span>)}</>
                : "No unique printed folio found"}
            {entry.page_end != null && entry.page_end !== entry.page_start && <> · {jump(entry.page_end, `End folio on PDF page ${entry.page_end}`)}</>}
          </p>
          {entry.body_title_matches.map((match, i) => <p key={i} className="mt-1 text-muted-foreground">
            {jump(match.page, `${match.kind === "section_index_candidate" ? "Title repeated in a section list" : "Matching title in the body"} on PDF page ${match.page}`)}
          </p>)}
          {conflict && <p className="mt-1 text-warning">Printed contents and body location differ.{bodySectionPage != null && <> {jump(bodySectionPage, `Section banner on PDF page ${bodySectionPage}`)}.</>} Both source observations are retained.</p>}
          {entry.source_lines.length > 0 && <details className="mt-1 text-muted-foreground">
            <summary className="cursor-pointer">Source contents text · PDF page {entry.source_lines[0].page}</summary>
            <p className="my-1 whitespace-pre-wrap">{entry.source_lines.map((line) => line.text).join("\n")}</p>
            {jump(entry.source_lines[0].page, "Inspect contents page")}
          </details>}
        </li>;
      })}
    </ol>
  </details>;
}
