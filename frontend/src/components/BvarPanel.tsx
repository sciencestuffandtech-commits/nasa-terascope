import type { BvarCell, BvarSummary, BvarDirKey, BvarSrc } from "../lib/api";
import { f } from "./ResultCard";

const pct = (v?: number | null) => (v == null || !Number.isFinite(v) ? "n/a" : `${(100 * v).toFixed(1)}%`);
const rng = (r?: [number, number] | null) => (r ? `${pct(r[0])} to ${pct(r[1])}` : "n/a");

export default function BvarPanel({ dir, src, cell, sum, err, hasCell }: {
  dir: BvarDirKey; src: BvarSrc; cell: BvarCell | null; sum: BvarSummary | null; err: string; hasCell: boolean;
}) {
  const soil = src === "soil";
  const S = soil ? "soil moisture" : "precipitation";
  const L = soil ? "S" : "P";
  const row = (label: string, d: BvarCell["pt"], tag: string) => d && (
    <tr>
      <td>{label}<br /><small>{tag}</small></td>
      <td>{f(d.median)}</td>
      <td>{f(d.lo)} to {f(d.hi)}</td>
      <td>{d.excludes_zero ? "yes" : "no"}</td>
    </tr>
  );
  const sets: [string, string][] = soil
    ? [["all", "All cells"], ["land", "Land"], ["ocean", "Coastal (land-mask ocean)"]]
    : [["all", "All cells"], ["land", "Land"], ["ocean", "Ocean"]];
  return (
    <div className="card">
      <p className="note">
        Bayesian VAR (3 monthly lags) on seasonal-fit residuals of temperature and {S}. About 10% of cells are expected to exclude zero by chance.
        {soil && " Soil moisture is NASA GLDAS Noah V2.1 model output (0-10 cm, land only, 2° grid)."}
      </p>
      {err && <p className="error">{err}</p>}
      {sum?.hypothesis && <p className="note"><b>Pre-registered (H-TP):</b> {sum.hypothesis}</p>}

      <h3>This cell</h3>
      {!hasCell && <p className="hint">Pick a location on the map.</p>}
      {hasCell && !cell && !err && <p className="hint">Loading…</p>}
      {cell && !cell.eligible && <p className="note">{cell.reason}</p>}
      {cell?.eligible && (<>
        <table className="cmp">
          <thead><tr><th>Direction</th><th>Median</th><th>90% interval</th><th>Excludes 0</th></tr></thead>
          <tbody>
            {row(`${soil ? "Soil moisture" : "Precipitation"} → later temperature`, cell.pt, "pre-registered")}
            {row(`Temperature → later ${S}`, cell.tp, "exploratory")}
          </tbody>
        </table>
        <p className="note">
          Sum of the three monthly lag coefficients, in standard deviations per standard deviation.
          {cell.forecast_gain != null && <> One-step temperature forecast gain over a model without {S}: {pct(cell.forecast_gain)} (a small or negative value means no predictive benefit).</>}
        </p>
      </>)}

      {sum && (<>
        <h3>Whole grid</h3>
        <table className="cmp">
          <thead><tr><th>Cells</th><th>n</th><th>{L}→T excl. 0</th><th>{L}→T negative</th><th>T→{L} excl. 0</th></tr></thead>
          <tbody>
            {sets.map(([k, name]) => { const s = sum.sets[k]; return s && (
              <tr key={k}><td>{name}</td><td>{s.n}</td><td>{pct(s.frac_PtoT_excl0)}</td><td>{pct(s.frac_PtoT_negative)}</td><td>{pct(s.frac_TtoP_excl0)}</td></tr>
            ); })}
          </tbody>
        </table>
        {sum.null && (
          <p className="note">
            Field null ({sum.null.n_reps} replicates, same year-shift applied to every cell, which keeps spatial correlation): {L}→T excluded zero in {rng(sum.null.PtoT_excl0)}, negative in {rng(sum.null.PtoT_negative)}.
          </p>
        )}
        {sum.calibration && (
          <p className="note">
            Null calibration on shifted real residuals: {L}→T {pct(sum.calibration.rate_PtoT_excl0)}, T→{L} {pct(sum.calibration.rate_TtoP_excl0)} (expected {pct(sum.calibration.expected)};
            pass window {rng(sum.calibration.pass_window)}; {sum.calibration.passed ? "passed" : "FAILED"}).
          </p>
        )}
        <p className="note">
          The map shows {dir === "pt" ? `${S} → later temperature` : `temperature → later ${S}`}.
        </p>
      </>)}
    </div>
  );
}