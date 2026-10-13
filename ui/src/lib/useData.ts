import { useEffect, useState } from "react";
export function useData<T>(url: string, revision: number) {
  const [state, setState] = useState<{
    data?: T;
    error?: string;
    loading: boolean;
  }>({ loading: true });
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true });
    fetch(url, {
      signal: controller.signal,
      headers: { Accept: "application/json" },
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            response.status === 404
              ? "This record was not found. It may have been moved or removed."
              : `The local service returned HTTP ${response.status}.`,
          );
        return response.json() as Promise<T>;
      })
      .then((data) => setState({ data, loading: false }))
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({
            error:
              error instanceof Error
                ? error.message
                : "The local service could not be reached.",
            loading: false,
          });
      });
    return () => controller.abort();
  }, [url, revision]);
  return state;
}
