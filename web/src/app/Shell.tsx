import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { ApiError, storeKey } from "../shared/api/client";
import { useOverview } from "../shared/api/queries";
import { ErrorState } from "../shared/ui/states";
import styles from "./Shell.module.css";

const NAV: Array<[string, string]> = [
  ["/", "Overview"],
  ["/sources", "Sources"],
  ["/review", "Review"],
  ["/items", "Files"],
  ["/releases", "Releases"],
  ["/takedowns", "Takedowns"],
];

function KeyForm() {
  const client = useQueryClient();
  const [key, setKey] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    storeKey(key.trim());
    void client.resetQueries();
  };
  return (
    <form className={styles.keyForm} onSubmit={submit}>
      <h1 className={styles.keyTitle}>Sign in to the refinery</h1>
      <p className={styles.muted}>Use an API key. Viewers can look; reviewers can decide held files; admins can take things down. The key is kept for this tab only.</p>
      <label className={styles.field}>
        <span>API key</span>
        <input type="password" autoComplete="off" required minLength={16} value={key} onChange={(e) => setKey(e.target.value)} />
      </label>
      <button type="submit" className={styles.primary}>
        Sign in
      </button>
    </form>
  );
}

export function Shell() {
  const q = useOverview();
  const needsKey = q.error instanceof ApiError && q.error.status === 401;
  return (
    <div className={styles.app}>
      <a href="#content" className={styles.skip}>
        Skip to content
      </a>
      <header className={styles.header}>
        <span className={styles.brand}>speech corpus refinery</span>
        <nav aria-label="Main" className={styles.nav}>
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={styles.link}>
              {label}
              {to === "/review" && q.data && q.data.held > 0 && <span className={styles.badge}>{q.data.held}</span>}
            </NavLink>
          ))}
        </nav>
      </header>
      <div id="content">
        {needsKey ? (
          <KeyForm />
        ) : q.isError ? (
          <div className={styles.pad}>
            <ErrorState error={q.error} what="the refinery" onRetry={() => void q.refetch()} />
          </div>
        ) : (
          <Outlet />
        )}
      </div>
    </div>
  );
}
