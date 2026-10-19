import { useState } from "react";
import { Outlet } from "react-router";
import { PanelLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sidebar } from "./Sidebar";
import { cn } from "@/lib/utils";

export function ChatLayout() {
  const [open, setOpen] = useState(true);
  return (
    <div className="flex h-dvh bg-background text-foreground">
      <aside
        className={cn(
          "hidden shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground transition-[width] md:flex",
          open ? "w-64" : "w-0 overflow-hidden border-r-0",
        )}
      >
        <Sidebar />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center gap-2 px-2">
          <Button variant="ghost" size="icon" aria-label="Toggle sidebar" onClick={() => setOpen((v) => !v)}>
            <PanelLeft className="size-5" />
          </Button>
          <span className="text-sm font-medium text-muted-foreground">Qwen3.8-27B · Livepeer</span>
        </header>
        <main className="flex min-h-0 flex-1 flex-col">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
