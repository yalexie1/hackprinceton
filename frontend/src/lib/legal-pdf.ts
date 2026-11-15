import { jsPDF } from "jspdf";
import type { DocumentDraft } from "./types";

const margin = 19;
const pageWidth = 215.9;
const contentWidth = pageWidth - 2 * margin;
const bottom = 254;
const ink: [number, number, number] = [29, 42, 39];
const muted: [number, number, number] = [83, 98, 92];

function plain(value: string): string {
  return value.normalize("NFKD")
    .replace(/[\u2010-\u2015\u2212]/g, "-")
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1 ($2)")
    .replace(/\*\*/g, "")
    .replace(/<[^>]+>/g, "")
    .replace(/[^\x20-\x7E\n]/g, "");
}

export function legalText(value: string): string {
  return plain(value
    .replace(/\[\[BLANK:\s*([^\]]+)\]\]/g, (_match, detail: string) =>
      detail.split(",")[0].trim().endsWith("_box") ? "[]" : `____________________ [${detail.trim()}]`,
    )
    .replace(/\{\{([^}]+)\}\}/g, (_match, key: string) =>
      key.trim().endsWith("_box") ? "[]" : `____________________ [${key.trim()}]`,
    )
    .replace(/\[(?: |x|X)\]/g, "[]"));
}

type Block = { kind: "heading" | "paragraph" | "list" | "quote" | "rule" | "table"; text: string; level?: number; rows?: string[][]; format?: string };

function blocks(markdown: string): Block[] {
  const result: Block[] = [];
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  let paragraph: string[] = [];
  let format = "";
  function flush() {
    if (paragraph.length) {
      result.push({ kind: "paragraph", text: paragraph.join(" "), format });
      paragraph = [];
      format = "";
    }
  }
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) { flush(); continue; }
    if (/^[-*+]$/.test(line)) { flush(); continue; }
    if (/^<!--/.test(line)) {
      flush();
      const match = line.match(/fmt:\s*(.*?)\s*-->/i);
      if (match) format = match[1];
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flush();
      result.push({ kind: "heading", level: heading[1].length, text: heading[2], format });
      format = "";
      continue;
    }
    if (/^[-*_]{3,}$/.test(line)) { flush(); result.push({ kind: "rule", text: "" }); continue; }
    if (line.startsWith("|")) {
      flush();
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
        if (!cells.every((cell) => /^:?-{3,}:?$/.test(cell))) rows.push(cells);
        i++;
      }
      i--;
      result.push({ kind: "table", text: "", rows, format });
      format = "";
      continue;
    }
    if (/^(?:[-*+]\s+|\d+\.\s+)/.test(line)) {
      flush();
      result.push({ kind: "list", text: line.replace(/^[-*+]\s+/, "- "), format });
      format = "";
      continue;
    }
    if (line.startsWith(">")) {
      flush(); result.push({ kind: "quote", text: line.replace(/^>\s?/, ""), format }); format = "";
      continue;
    }
    paragraph.push(line);
  }
  flush();
  return result;
}

export function createLegalPdf(draft: DocumentDraft): jsPDF {
  const pdf = new jsPDF({ unit: "mm", format: "letter", compress: true });
  let y = 25;
  function page() {
    pdf.addPage();
    y = 25;
  }
  function ensure(height: number) { if (y + height > bottom) page(); }
  function style(size: number, bold = false, color = ink) {
    pdf.setFont("times", bold ? "bold" : "normal");
    pdf.setFontSize(size);
    pdf.setTextColor(...color);
  }
  function drawLine(line: string, x: number, baseline: number, size: number) {
    let cursor = x;
    for (const [index, part] of line.split("[]").entries()) {
      if (index) {
        pdf.setDrawColor(...ink);
        pdf.setLineWidth(0.3);
        pdf.rect(cursor + 0.35, baseline - 2.9, 3.2, 3.2);
        cursor += 4.5;
      }
      if (part) { pdf.text(part, cursor, baseline); cursor += pdf.getTextWidth(part); }
    }
    return cursor;
  }
  function write(value: string, options: { size?: number; bold?: boolean; indent?: number; after?: number; color?: [number, number, number]; keep?: number; } = {}) {
    const size = options.size ?? 10.5;
    const indent = options.indent ?? 0;
    const lineHeight = size * 0.45;
    style(size, options.bold, options.color);
    const lines = pdf.splitTextToSize(legalText(value), contentWidth - indent) as string[];
    ensure(Math.max(options.keep ?? 0, Math.min(lines.length, 2) * lineHeight + (options.after ?? 2.8)));
    for (const line of lines) {
      ensure(lineHeight);
      drawLine(line, margin + indent, y, size);
      y += lineHeight;
    }
    y += options.after ?? 2.8;
  }

  // The legal team's disclaimer is part of the draft, not a footnote.
  const disclaimerText = plain(draft.disclaimer);
  style(10.5, true, [85, 48, 29]);
  const disclaimerLines = pdf.splitTextToSize(disclaimerText, contentWidth - 8) as string[];
  const disclaimerHeight = Math.max(17, disclaimerLines.length * 5 + 8);
  pdf.setFillColor(252, 244, 230);
  pdf.setDrawColor(180, 140, 93);
  pdf.rect(margin, y - 5, contentWidth, disclaimerHeight, "FD");
  disclaimerLines.forEach((line, index) => pdf.text(line, margin + 4, y + index * 5));
  y += disclaimerHeight + 5;

  // Preserve authored legal language and statutory notices. Only presentation changes here.
  for (const block of blocks(draft.markdown)) {
    if (block.kind === "rule") {
      ensure(8); pdf.setDrawColor(184, 193, 188); pdf.line(margin, y + 2, pageWidth - margin, y + 2); y += 8;
    } else if (block.kind === "heading") {
      const level = block.level ?? 3;
      const size = level === 1 ? 15 : level === 2 ? 12.5 : 11.5;
      y += level <= 2 ? 4 : 2;
      write(block.text, { size, bold: true, after: 3.5, keep: 18 });
      if (level <= 2) { pdf.setDrawColor(177, 193, 183); pdf.line(margin, y - 1, pageWidth - margin, y - 1); y += 2; }
    } else if (block.kind === "paragraph" || block.kind === "quote") {
      const isNotice = /bold|boxed/i.test(block.format ?? "");
      const size = /12pt/i.test(block.format ?? "") ? 12 : 10.5;
      const start = y;
      const boldLead = block.text.match(/^\*\*([^*]+)\*\*(?:\s+|$)(.*)$/s);
      if (boldLead && !isNotice) {
        write(boldLead[1], { size, bold: true, indent: block.kind === "quote" ? 5 : 0, after: boldLead[2] ? 1.2 : 3.2, keep: 12 });
        if (boldLead[2]) write(boldLead[2], { size, indent: block.kind === "quote" ? 5 : 0, after: 3.2 });
      } else {
        write(block.text, { size, bold: isNotice, indent: block.kind === "quote" ? 5 : 0, after: 3.2 });
      }
      if (/boxed/i.test(block.format ?? "") && start >= 25 && y < bottom) {
        pdf.setDrawColor(83, 98, 92); pdf.rect(margin - 2, start - 4, contentWidth + 4, y - start + 5);
      }
    } else if (block.kind === "list") {
      write(block.text, { indent: 5, after: 1.8 });
    } else if (block.kind === "table" && block.rows?.length) {
      const rows = block.rows;
      const columns = Math.max(...rows.map((row) => row.length));
      const firstWidth = columns === 2 ? contentWidth * 0.36 : contentWidth / columns;
      const widths = Array.from({ length: columns }, (_, index) => columns === 2 ? (index === 0 ? firstWidth : contentWidth - firstWidth) : contentWidth / columns);
      for (let rowIndex = 0; rowIndex < rows.length; rowIndex++) {
        style(9.5, rowIndex === 0);
        const wrapped = widths.map((width, column) => pdf.splitTextToSize(legalText(rows[rowIndex][column] ?? ""), width - 5) as string[]);
        const height = Math.max(9, Math.max(...wrapped.map((cell) => cell.length)) * 4.3 + 4);
        ensure(height);
        let x = margin;
        for (let column = 0; column < columns; column++) {
          if (rowIndex === 0) pdf.setFillColor(234, 239, 235);
          else pdf.setFillColor(255, 255, 255);
          pdf.setDrawColor(183, 194, 186);
          pdf.rect(x, y, widths[column], height, "FD");
          style(9.5, rowIndex === 0);
          wrapped[column].forEach((line, lineIndex) => drawLine(line, x + 2.5, y + 5 + lineIndex * 4.3, 9.5));
          if (/^signature$/i.test(rows[rowIndex][0] ?? "") && column > 0) {
            pdf.setDrawColor(...ink); pdf.line(x + 3, y + height - 2.5, x + widths[column] - 3, y + height - 2.5);
          }
          x += widths[column];
        }
        y += height;
      }
      y += 5;
    }
  }

  if (draft.unfilled_placeholders.length) {
    y += 4;
    write("Information still needed before signing", { size: 12.5, bold: true, keep: 20 });
    for (const key of [...new Set(draft.unfilled_placeholders)].filter((key) => !key.endsWith("_box"))) {
      write(`- ${key}: ____________________`, { size: 10, after: 1.5 });
    }
  }
  y += 4;
  write("Legal requirements review", { size: 12.5, bold: true, keep: 20 });
  if (!draft.statutory_checks.length) {
    write("Statutory requirements have not been checked for this draft.", { size: 10.5 });
  }
  for (const check of draft.statutory_checks) {
    const title = `${check.satisfied ? "Confirmed" : "Pending"} - ${check.requirement_id ? `${check.requirement_id}: ` : ""}${check.requirement}`;
    const explanation = `${check.citation}${check.note ? ` - ${check.note}` : ""}`;
    style(10.5, true);
    const titleHeight = (pdf.splitTextToSize(legalText(title), contentWidth) as string[]).length * 10.5 * 0.45;
    style(10);
    const explanationHeight = (pdf.splitTextToSize(legalText(explanation), contentWidth - 5) as string[]).length * 10 * 0.45;
    ensure(titleHeight + explanationHeight + 3);
    write(title, { size: 10.5, bold: true, color: check.satisfied ? [35, 89, 58] : [124, 69, 29], after: 0.8 });
    write(explanation, { size: 10, color: muted, indent: 5, after: 2 });
  }

  const pages = pdf.getNumberOfPages();
  for (let number = 1; number <= pages; number++) {
    pdf.setPage(number);
    pdf.setDrawColor(177, 193, 183);
    pdf.line(margin, 18, pageWidth - margin, 18);
    pdf.line(margin, 263, pageWidth - margin, 263);
    style(8.5, true, muted); pdf.text("LETO  |  LEGAL DOCUMENT DRAFT", margin, 14);
    style(8.5, false, muted); pdf.text("Review and complete before signing", margin, 269);
    pdf.text(`${number} / ${pages}`, pageWidth - margin, 269, { align: "right" });
  }
  return pdf;
}

export function exportLegalPdf(draft: DocumentDraft): void {
  const name = `${draft.doc_type}-${draft.state}`.toLowerCase().replace(/[^a-z0-9-]+/g, "-");
  createLegalPdf(draft).save(`${name}-draft.pdf`);
}
