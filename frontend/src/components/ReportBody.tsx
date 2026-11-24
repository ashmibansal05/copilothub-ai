import { Fragment } from "react";

/** Safe, dependency-free display for the subset of Markdown saved in project reports.
 * It never evaluates HTML and always escapes text through React.
 */
export default function ReportBody({ body }: { body: string }) {
  const lines = (body || "").split(/\r?\n/);
  const elements: React.ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const fence = line.match(/^\s*(`{3,}|~{3,})(.*)$/);
    if (fence) {
      const marker = fence[1][0];
      const length = fence[1].length;
      const language = fence[2].trim();
      const content: string[] = [];
      index += 1;
      while (index < lines.length && !(lines[index].trim().startsWith(marker.repeat(length)))) {
        content.push(lines[index]);
        index += 1;
      }
      elements.push(<div key={`code-${index}`} className="my-3 overflow-hidden rounded-lg border border-slate-200 bg-slate-900">
        {language && <div className="border-b border-slate-700 px-3 py-1 text-xs text-slate-300">{language}</div>}
        <pre className="overflow-x-auto p-4 text-xs leading-6 text-slate-100"><code>{content.join("\n")}</code></pre>
      </div>);
      index += 1;
      continue;
    }
    const heading = line.match(/^(#{3,5})\s+(.+)$/);
    if (heading) {
      elements.push(<h3 key={`heading-${index}`} className="mt-5 mb-2 break-words font-semibold text-slate-900">{heading[2]}</h3>);
      index += 1;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ""));
        index += 1;
      }
      elements.push(<ul key={`list-${index}`} className="my-2 list-disc space-y-1 pl-5">
        {items.map((item, i) => <li key={i} className="break-words">{item}</li>)}
      </ul>);
      continue;
    }
    if (!line.trim()) { index += 1; continue; }
    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim() &&
           !/^\s*(`{3,}|~{3,})/.test(lines[index]) &&
           !/^#{3,5}\s+/.test(lines[index]) &&
           !/^\s*[-*]\s+/.test(lines[index])) {
      paragraph.push(lines[index]);
      index += 1;
    }
    elements.push(<p key={`paragraph-${index}`} className="my-2 whitespace-pre-wrap break-words leading-relaxed">{paragraph.join("\n")}</p>);
  }
  return <div className="text-sm text-slate-800">{elements.map((el, i) => <Fragment key={i}>{el}</Fragment>)}</div>;
}
