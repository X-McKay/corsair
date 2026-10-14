import { useEffect, useState } from "react";

const REFRESH_MS = 30_000;
const TIMEOUT_MS = 15_000;

export function useData<T>(url: string, revision: number) {
  const [state, setState] = useState<{
    data?: T;
    error?: string;
    loading: boolean;
  }>({ loading: true });
  useEffect(() => {
    let stopped = false;
    let active = false;
    let controller: AbortController | undefined;
    let next: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      if (stopped || active) return;
      active = true;
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), TIMEOUT_MS);
      try {
        const response = await fetch(url, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          const body: unknown = await response.json().catch(() => null);
          const detail =
            body &&
            typeof body === "object" &&
            "error" in body &&
            typeof body.error === "string"
              ? body.error
              : undefined;
          throw new Error(
            detail ||
              (response.status === 404
                ? "This record was not found. It may have been moved or removed."
                : `The Corsair service returned HTTP ${response.status}.`),
          );
        }
        const data = (await response.json()) as T;
        if (!stopped)
          setState({
            data,
            loading: false,
          });
      } catch (error) {
        if (!stopped)
          setState({
            error: controller.signal.aborted
              ? "The Corsair service did not respond within 15 seconds. Check service connectivity and the configured data sources."
              : error instanceof TypeError
                ? "The Corsair service could not be reached. Check the service address and network connection."
                : error instanceof SyntaxError
                  ? "The Corsair service returned an invalid response. Check API routing and service logs."
                  : error instanceof Error
                    ? error.message
                    : "The Corsair service could not be reached.",
            loading: false,
          });
      } finally {
        clearTimeout(timeout);
        active = false;
        if (!stopped && document.visibilityState === "visible")
          next = setTimeout(load, REFRESH_MS);
      }
    };
    const visibility = () => {
      clearTimeout(next);
      if (document.visibilityState === "visible") void load();
    };
    setState({ loading: true });
    void load();
    document.addEventListener("visibilitychange", visibility);
    return () => {
      stopped = true;
      clearTimeout(next);
      controller?.abort();
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [url, revision]);
  return state;
}
