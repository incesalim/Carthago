"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useText } from "@/i18n/use-text";
import styles from "./sector-report.module.css";

/**
 * Topic navigation. The strip WRAPS at every width: a label is either on the
 * first row or on a later one, never cut at the toolbar edge, so it is readable
 * without hover, scroll or a fade hint. Only reading position is client state;
 * section content and figures are server-rendered.
 */
export function SectorContents({ sections, controls }: {
  sections: { id: string; label: string }[];
  controls?: ReactNode;
}) {
  const tx = useText();
  const [active, setActive] = useState(sections[0]?.id);
  const nav = useRef<HTMLDivElement>(null);
  const ids = sections.map(section => section.id).join("|");

  useEffect(() => {
    const nodes = ids.split("|").map(id => document.getElementById(id)).filter((node): node is HTMLElement => !!node);
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const edge = (nav.current?.getBoundingClientRect().bottom ?? 100) + 48;
        let current: HTMLElement | undefined = nodes[0];
        for (const node of nodes) {
          if (node.getBoundingClientRect().top <= edge) current = node;
        }
        if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 4) current = nodes.at(-1);
        if (current) setActive(current.id);
      });
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [ids]);

  return <div ref={nav} className={styles.toolbar}>
    <nav aria-label={tx("On this page")} className={styles.contents}>
      {sections.map(({ id, label }) => <a key={id} href={`#${id}`} title={tx(label)}
        onClick={() => setActive(id)}
        aria-current={active === id ? "location" : undefined}>{tx(label)}</a>)}
    </nav>
    {controls && <div className={styles.range}><span>{tx("Chart period")}</span>{controls}</div>}
  </div>;
}
