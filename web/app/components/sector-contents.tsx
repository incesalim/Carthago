"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useText } from "@/i18n/use-text";
import { cn } from "@/app/lib/cn";
import styles from "./sector-report.module.css";

/** Only reading position is client state; section content and figures are server-rendered. */
export function SectorContents({ sections, controls }: {
  sections: { id: string; label: string }[];
  controls?: ReactNode;
}) {
  const tx = useText();
  const [active, setActive] = useState(sections[0]?.id);
  const nav = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLElement>(null);
  // Edge fades say "there is more this way" only while it is true, so a tab
  // clipped at the toolbar edge never reads as the end of the list.
  const [{ start, end }, setEdges] = useState({ start: true, end: true });
  const ids = sections.map(section => section.id).join("|");

  const measure = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    setEdges({ start: el.scrollLeft <= 1, end: el.scrollLeft >= max - 1 });
  }, []);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    if (el.firstElementChild) ro.observe(el.firstElementChild);
    return () => {
      el.removeEventListener("scroll", measure);
      ro.disconnect();
    };
  }, [measure]);

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
    <div className={styles.contentsWrap}>
      <nav ref={scroller} aria-label={tx("On this page")} className={styles.contents}>
        {sections.map(({ id, label }) => <a key={id} href={`#${id}`} onClick={() => setActive(id)} aria-current={active === id ? "location" : undefined}>{tx(label)}</a>)}
      </nav>
      <div aria-hidden className={cn(styles.contentsFade, styles.contentsFadeStart)} data-hidden={start} />
      <div aria-hidden className={cn(styles.contentsFade, styles.contentsFadeEnd)} data-hidden={end} />
    </div>
    {controls && <div className={styles.range}><span>{tx("Chart period")}</span>{controls}</div>}
  </div>;
}
