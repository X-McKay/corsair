import { useEffect, useState } from "react";
import {
  Boxes,
  ChartColumn,
  GitCompareArrows,
  ChevronRight,
  FlaskConical,
  LayoutDashboard,
  Menu,
  RefreshCw,
  ShieldCheck,
  X,
  AlertCircle,
  PanelLeftClose,
} from "lucide-react";
import { ThemeSelect } from "./components/ThemeProvider";
import { Badge, Notice, State } from "./components/evidence";
import { type EvaluationList } from "./lib/data";
import { usePath, Link } from "./lib/navigation";
import { useData } from "./lib/useData";
import { Overview } from "./pages/Overview";
import { Evaluations } from "./pages/Evaluations";
import { Detail } from "./pages/EvaluationDetail";
import { Runtime } from "./pages/Runtime";
import { Metrics } from "./pages/Metrics";
import { Experiments } from "./pages/Experiments";
export function App() {
  const path = usePath();
  const [revision, setRevision] = useState(0);
  const [menu, setMenu] = useState(false);
  const retry = () => setRevision((value) => value + 1);
  const data = useData<EvaluationList>("/api/evaluations", revision);
  useEffect(() => {
    setMenu(false);
    document.getElementById("main-content")?.focus();
  }, [path]);
  useEffect(() => {
    if (!menu) return;
    const drawer = document.querySelector<HTMLElement>(".sidebar");
    const first = drawer?.querySelector<HTMLElement>("a,button,select");
    first?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenu(false);
        document.querySelector<HTMLElement>(".mobile-menu")?.focus();
      }
      if (event.key === "Tab" && drawer) {
        const controls = Array.from(
          drawer.querySelectorAll<HTMLElement>("a,button,select"),
        );
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        }
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menu]);
  const page = path.startsWith("/evaluations")
    ? "Evaluations"
    : path === "/metrics" || path === "/agents"
      ? "Agents"
      : path === "/experiments"
        ? "Experiments"
        : path === "/runtime"
          ? "Runtime readiness"
          : "Overview";
  const parts = path.split("/").filter(Boolean);
  let detail: { agent: string; run: string } | undefined;
  if (parts[0] === "evaluations" && parts.length === 3) {
    try {
      detail = {
        agent: decodeURIComponent(parts[1]),
        run: decodeURIComponent(parts[2]),
      };
    } catch {}
  }
  return (
    <div className="app">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      {menu && (
        <button
          aria-label="Close navigation overlay"
          className="nav-overlay"
          onClick={() => setMenu(false)}
        />
      )}
      <aside className={`sidebar ${menu ? "open" : ""}`}>
        <Link to="/" className="brand">
          <span className="brand-mark">
            <ShieldCheck size={24} />
          </span>
          <span>
            Corsair<small>Evaluation workspace</small>
          </span>
        </Link>
        <button
          className="mobile-close icon-button"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        >
          <X size={20} />
        </button>
        <div className="nav-label">Workspace</div>
        <nav aria-label="Main navigation">
          {[
            { to: "/", label: "Overview", icon: <LayoutDashboard size={18} /> },
            {
              to: "/evaluations",
              label: "Evaluations",
              icon: <FlaskConical size={18} />,
            },
            {
              to: "/agents",
              label: "Agents",
              icon: <ChartColumn size={18} />,
            },
            {
              to: "/experiments",
              label: "Experiments",
              icon: <GitCompareArrows size={18} />,
            },
            {
              to: "/runtime",
              label: "Runtime readiness",
              icon: <Boxes size={18} />,
            },
          ].map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={`nav-link ${page === item.label ? "selected" : ""}`}
              aria-current={page === item.label ? "page" : undefined}
            >
              {item.icon}
              {item.label}
              {item.label === "Evaluations" && data.data && (
                <span className="nav-count">{data.data.runs.length}</span>
              )}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-note">
            <span className="status-dot" />
            <b>Local workspace</b>
            <span>Read-only inspection</span>
          </div>
          <label className="theme-label">
            Appearance
            <ThemeSelect />
          </label>
          <div className="sidebar-foot">
            <ShieldCheck size={13} />
            Local evaluation records
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <button
              className="mobile-menu icon-button"
              aria-label="Open navigation"
              aria-expanded={menu}
              onClick={() => setMenu(!menu)}
            >
              <Menu size={20} />
            </button>
            <PanelLeftClose size={16} className="desktop-mark" />
            <span className="muted">Workspace</span>
            <ChevronRight size={14} />
            <b>{page}</b>
          </div>
          <div>
            <Badge>
              <span className="status-dot" />
              Read only
            </Badge>
            <button
              className="icon-button"
              aria-label="Refresh evidence"
              onClick={retry}
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          {path === "/runtime" ? (
            <Runtime revision={revision} retry={retry} />
          ) : path === "/agents" || path === "/metrics" ? (
            <Metrics revision={revision} retry={retry} />
          ) : path === "/experiments" ? (
            <Experiments revision={revision} retry={retry} />
          ) : detail ? (
            <Detail {...detail} revision={revision} retry={retry} />
          ) : path !== "/" && path !== "/evaluations" ? (
            <div className="empty-state">
              <AlertCircle size={28} />
              <h1>Page not found</h1>
              <Link to="/" className="button">
                Back to overview
              </Link>
            </div>
          ) : !data.data ? (
            <State loading={data.loading} error={data.error} retry={retry} />
          ) : (
            <>
              {data.data.warnings.map((warning, i) => (
                <Notice key={i} tone="warning">
                  {warning}
                </Notice>
              ))}
              {path === "/evaluations" ? (
                <Evaluations data={data.data} />
              ) : (
                <Overview data={data.data} revision={revision} retry={retry} />
              )}
            </>
          )}
          <footer>
            <span>
              Corsair <span className="footer-dot">/</span> Agent evaluation &
              evidence
            </span>
            <span>Local records · No automatic refresh</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
