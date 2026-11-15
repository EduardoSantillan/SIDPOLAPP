import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ApiError } from "./lib/api";
import { AuthProvider } from "./lib/auth";
import "./styles.css";

// Un error 4xx (por ejemplo «sin resultados») no mejora al repetirlo; una caída del servidor sí puede.
const cache = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 30_000, retry: (n, e) => n < 1 && !(e instanceof ApiError && e.status > 0 && e.status < 500) } },
});

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <QueryClientProvider client={cache}>
      <BrowserRouter>
        <AuthProvider><App /></AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
