import { useState } from "react";
import { Outlet } from "react-router";
import { PanelLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { Sidebar } from "./Sidebar";
import { cn } from "@/lib/utils";

// Desktop (md and up): a sidebar that the header button collapses. Phones: the same button opens the
// sidebar as a slide-in drawer, which closes when a chat is picked, a new chat starts, or on tap outside.
export function ChatLayout() {
  const desktop = useMediaQuery("(min-width: 768px)");
  const [open, setOpen] = useState(true);
  const [drawer, setDrawer] = useState(false);
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
      {!desktop && (
        <Sheet open={drawer} onOpenChange={setDrawer}>
          <SheetContent side="left" showCloseButton={false} className="w-72 max-w-[85vw] gap-0 bg-sidebar p-0 text-sidebar-foreground">
            <SheetTitle className="sr-only">Chats</SheetTitle>
            <SheetDescription className="sr-only">Your conversations and account menu</SheetDescription>
            <Sidebar onNavigate={() => setDrawer(false)} />
          </SheetContent>
        </Sheet>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center gap-2 px-2">
          <Button
            variant="ghost"
            size="icon"
            aria-label={desktop ? "Toggle sidebar" : "Open menu"}
            onClick={() => (desktop ? setOpen((v) => !v) : setDrawer(true))}
          >
            <PanelLeft className="size-5" />
          </Button>
          <span className="truncate text-sm font-medium text-muted-foreground">Qwen3.8-27B · Livepeer</span>
        </header>
        <main className="flex min-h-0 flex-1 flex-col">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
