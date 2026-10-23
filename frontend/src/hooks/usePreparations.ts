import { useEffect, useState } from "react";
import { activatePreparation, listPreparations, savePreparation, type Preparation, type PreparationInput } from "../lib/preparations";
export function usePreparations() {
  const [items, setItems] = useState<Preparation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    listPreparations(controller.signal).then(setItems).catch(() => { if (!controller.signal.aborted) setError("Unable to load your preparations. Refresh the page to try again."); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);
  async function save(input: PreparationInput, id?: string) {
    if (busy) return null;
    setBusy(true); setError("");
    try {
      const item = await savePreparation(input, id);
      // Retain a successful save even if the separate activation request fails.
      setItems(previous => [item, ...previous.filter(p => p.id !== item.id)]);
      try {
        await activatePreparation(item.id);
        setItems(previous => previous.map(p => ({ ...p, active: p.id === item.id })));
        return { item, activated: true };
      } catch {
        setError("Preparation saved, but it could not be selected for Desktop. Retry Save & use preparation.");
        return { item, activated: false };
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to save preparation."); return null; }
    finally { setBusy(false); }
  }
  return { items, loading, error, busy, save };
}
