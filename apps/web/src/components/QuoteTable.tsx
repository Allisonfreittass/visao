import type { QuoteTable as Table } from "../api";

/** Which bubble is the table's text, to draw the table in its place (or -1). */
export function tableBubble(parts: string[] | null | undefined, table: Table | null | undefined): number {
  if (!parts || !table) return -1;
  return parts.lastIndexOf(table.text);
}

/** "Considerei saída de Guarulhos (GRU)…; 2 adultos": what the quote assumed, in one line. */
export function assumedLine(assumed: Record<string, string> | undefined): string {
  const said = Object.values(assumed ?? {}).filter(Boolean);
  return said.length ? `Considerando: ${said.join(" · ")}` : "";
}

/** The options of a live quote, from the cheapest; numbers come from the server, never the model. */
export function QuoteTable({ table }: { table: Table }) {
  const assumed = assumedLine(table.assumed);
  return (
    <figure className="quote-table" aria-label={`Opções: ${table.title}`}>
      <figcaption>
        <strong>{table.title}</strong>
        <span>para {table.travelers} {table.travelers === 1 ? "pessoa" : "pessoas"}</span>
      </figcaption>
      <table>
        <thead>
          <tr>
            <th scope="col">Opção</th>
            <th scope="col">Datas</th>
            <th scope="col" className="quote-table-total">Total</th>
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, n) => (
            <tr key={`${row.option}-${row.dates}`} className={n === 0 ? "quote-table-best" : undefined}>
              <td>
                {row.option}
                {row.sites.length > 0 && <small>{row.sites.join(" · ")}</small>}
              </td>
              <td>{row.dates || "—"}</td>
              <td className="quote-table-total">{row.total_text}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {table.notes.map((note) => <p key={note} className="quote-table-note">{note}</p>)}
      {assumed && <p className="quote-table-assumed">{assumed}</p>}
    </figure>
  );
}
