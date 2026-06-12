// UI manifest for the scriptures app. Auto-discovered by
// web/src/apps/registry.js via import.meta.glob at build time.
import { lazy } from "react";
import { BookOpen } from "lucide-react";

export default [
  { id: "scriptures", name: "Scriptures", icon: BookOpen, component: lazy(() => import("./ScripturesApp")), singleton: true },
];
