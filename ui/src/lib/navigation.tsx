import { useEffect, useState, type ReactNode, type MouseEvent } from "react";
export function usePath() {
  const [path, setPath] = useState(location.pathname);
  useEffect(() => {
    const change = () => setPath(location.pathname);
    addEventListener("popstate", change);
    return () => removeEventListener("popstate", change);
  }, []);
  return path;
}
export function Link({
  to,
  children,
  className,
  ...props
}: {
  to: string;
  children: ReactNode;
  className?: string;
  "aria-current"?: "page";
}) {
  return (
    <a
      href={to}
      className={className}
      {...props}
      onClick={(event: MouseEvent) => {
        if (
          event.button ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey
        )
          return;
        event.preventDefault();
        history.pushState({}, "", to);
        dispatchEvent(new PopStateEvent("popstate"));
        window.scrollTo(0, 0);
      }}
    >
      {children}
    </a>
  );
}
