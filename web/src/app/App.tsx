import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import { useState } from "react";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";

import { ItemsPage } from "../features/items/ItemsPage";
import { OverviewPage } from "../features/overview/OverviewPage";
import { ReleasesPage } from "../features/releases/ReleasesPage";
import { ReviewPage } from "../features/review/ReviewPage";
import { SourcesPage } from "../features/sources/SourcesPage";
import { TakedownsPage } from "../features/takedowns/TakedownsPage";
import { ApiError } from "../shared/api/client";
import { Shell } from "./Shell";

export const routes = [
  {
    path: "/",
    element: <Shell />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "sources", element: <SourcesPage /> },
      { path: "review", element: <ReviewPage /> },
      { path: "items", element: <ItemsPage /> },
      { path: "releases", element: <ReleasesPage /> },
      { path: "takedowns", element: <TakedownsPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
];

export function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (n, e) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 2,
        refetchOnWindowFocus: false,
      },
    },
  });
}

export function App() {
  const [client] = useState(makeClient);
  const [router] = useState(() => createBrowserRouter(routes));
  return (
    <QueryClientProvider client={client}>
      <MotionConfig reducedMotion="user">
        <RouterProvider router={router} future={{ v7_startTransition: true }} />
      </MotionConfig>
    </QueryClientProvider>
  );
}
