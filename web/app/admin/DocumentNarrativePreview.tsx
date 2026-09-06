"use client";

import { useState } from "react";
import { nf } from "@/app/lib/chart-format";

export type Narrative = { id: string; kind: string; text: string; span_ids: (string | number)[];
  heading_path: { id: string; text: string }[]; table_ids: string[] };
type LayoutNode = { kind: "element" | "list_item_candidate"; element_ids: string[] }
  | { kind: "sequence" | "unresolved_overlap"; axis?: "x" | "y"; children: LayoutNode[] };
export type ReadingLayout = { tree: LayoutNode | null; issues: { kind: string }[] };

function sourceIds(node: LayoutNode): string[] {
  return "element_ids" in node ? node.element_ids : node.children.flatMap(sourceIds);
}

function SourceElements({ elements, raw = false }: { elements: Narrative[]; raw?: boolean }) {
  return <div className="border-b border-border py-3">
    <div className="flex flex-wrap gap-x-3 text-[10px] text-faint">
      {elements.map((element) => <span key={element.id} className="font-mono"
        title={`Source spans: ${element.span_ids.join(", ")}`}>{element.id}</span>)}
      {raw && <span>{elements[0].kind.replaceAll("_", " ")}</span>}
    </div>
    {raw && elements[0].heading_path.length > 0 && <p className="mt-1 text-[10px] text-muted-foreground">
      {elements[0].heading_path.map((heading) => heading.text).join(" / ")}</p>}
    {elements.some((element) => element.table_ids.length > 0) && <p className="mt-1 text-[10px] text-faint">
      Table: {[...new Set(elements.flatMap((element) => element.table_ids))].join(", ")}</p>}
    <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed">{elements.map((element) => raw ? element.text : element.text.trim()).join(" ")}</p>
  </div>;
}

function LayoutBranch({ node, elements }: { node: LayoutNode; elements: Map<string, Narrative> }) {
  if ("element_ids" in node) {
    const members = node.element_ids.map((id) => elements.get(id));
    if (members.some((element) => !element)) return <p role="alert" className="text-xs text-warning">Reading view references missing source text. Inspect the stored order.</p>;
    return <SourceElements elements={members as Narrative[]} />;
  }
  const columns = node.axis === "x";
  return <div className={columns ? "grid gap-x-5 overflow-x-auto" : ""}
    style={columns ? { gridTemplateColumns: `repeat(${node.children.length}, minmax(12rem, 1fr))` } : undefined}>
    {node.kind === "unresolved_overlap" && <p className="mt-2 text-xs text-warning">Order unresolved in this area; stored order retained.</p>}
    {node.children.map((child, index) => <LayoutBranch key={index} node={child} elements={elements} />)}
  </div>;
}

export default function DocumentNarrativePreview({ elements, layout }: { elements: Narrative[]; layout?: ReadingLayout }) {
  const [useLayout, setUseLayout] = useState(true);
  const ids = layout?.tree ? sourceIds(layout.tree) : [];
  const validLayout = ids.length === elements.length && new Set(ids).size === ids.length
    && elements.every((element) => ids.includes(element.id));
  return <details className="mt-5" open>
    <summary className="cursor-pointer text-xs font-semibold">Paragraphs and headings · {nf(elements.length, 0)} candidates</summary>
    <p className="my-2 text-xs text-faint">Source wording is retained. Paragraph boundaries, heading context and table membership await review.</p>
    {layout && <div className="my-2 text-xs text-muted-foreground">
      <label><input type="checkbox" checked={useLayout} onChange={(event) => setUseLayout(event.target.checked)} className="mr-2" />Arrange text by its position on the page</label>
      <p className="mt-1">Columns and list links follow source positions. Reading order still needs review.</p>
      {layout.issues.length > 0 && <p className="mt-1 text-warning">{nf(layout.issues.length, 0)} areas have unresolved order.</p>}
    </div>}
    {layout && !validLayout && <p role="alert" className="text-xs text-warning">Reading view has incomplete source references. All text is shown in stored order.</p>}
    {useLayout && validLayout && layout?.tree ? <LayoutBranch node={layout.tree} elements={new Map(elements.map((element) => [element.id, element]))} />
      : elements.map((element) => <SourceElements key={element.id} elements={[element]} raw />)}
  </details>;
}
