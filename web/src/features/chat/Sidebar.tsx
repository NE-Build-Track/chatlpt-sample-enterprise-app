import { Link, NavLink, useNavigate, useParams } from "react-router";
import { useState } from "react";
import { BarChart3, History, LogOut, MoreHorizontal, Pencil, Plus, Shield, Trash2 } from "lucide-react";
import { useMe, useLogout } from "@/api/auth";
import { useConversations, useDeleteConversation, useRenameConversation } from "@/api/conversations";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { UsageDialog } from "@/features/usage/UsageDialog";
import { cn } from "@/lib/utils";
import { ClearHistoryDialog } from "./ClearHistoryDialog";

function groupLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const days = Math.floor((today.setHours(0, 0, 0, 0) - new Date(date).setHours(0, 0, 0, 0)) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return "Previous 7 days";
  if (days < 30) return "Previous 30 days";
  return "Older";
}

// ``onNavigate`` lets the mobile drawer close when the person picks a chat or starts a new one.
export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const { conversationId } = useParams();
  const conversations = useConversations();
  const rename = useRenameConversation();
  const remove = useDeleteConversation();
  const [usageOpen, setUsageOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);

  const groups = new Map<string, typeof conversations.data>();
  for (const c of conversations.data ?? []) {
    const label = groupLabel(c.updated_at);
    groups.set(label, [...(groups.get(label) ?? []), c]);
  }

  function onNew() {
    navigate("/"); // the welcome screen; the conversation is created with its first message
    onNavigate?.();
  }

  async function onRename(id: string, current: string) {
    const title = window.prompt("Rename conversation", current);
    if (title && title.trim() && title !== current) await rename.mutateAsync({ id, title: title.trim() });
  }

  async function onDelete(id: string) {
    if (!window.confirm("Delete this conversation? Usage records are kept.")) return;
    await remove.mutateAsync(id);
    if (conversationId === id) navigate("/");
  }

  return (
    <div className="flex h-full flex-col">
      <div className="p-2">
        <Button variant="outline" className="w-full justify-start gap-2" onClick={onNew}>
          <Plus className="size-4" /> New chat
        </Button>
      </div>
      <ScrollArea className="min-h-0 flex-1 px-2">
        {[...groups.entries()].map(([label, items]) => (
          <div key={label} className="mb-3">
            <div className="px-2 py-1 text-xs font-medium text-muted-foreground">{label}</div>
            {items?.map((c) => (
              <div key={c.id} className="group relative">
                <NavLink
                  to={`/c/${c.id}`}
                  className={({ isActive }) =>
                    cn(
                      "block truncate rounded-md px-2 py-1.5 pr-8 text-sm hover:bg-sidebar-accent",
                      isActive && "bg-sidebar-accent font-medium",
                    )
                  }
                  title={c.title}
                  onClick={onNavigate}
                >
                  {c.title}
                </NavLink>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      aria-label="Conversation actions"
                      // Always visible on touch screens and on the open chat; elsewhere on hover.
                      className="absolute right-1 top-1 rounded p-1 opacity-0 group-hover:opacity-100 group-has-[[aria-current=page]]:opacity-100 focus:opacity-100 data-[state=open]:opacity-100 hover:bg-sidebar-accent [@media(hover:none)]:opacity-100"
                    >
                      <MoreHorizontal className="size-4" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => onRename(c.id, c.title)}>
                      <Pencil className="size-4" /> Rename
                    </DropdownMenuItem>
                    <DropdownMenuItem variant="destructive" onClick={() => onDelete(c.id)}>
                      <Trash2 className="size-4" /> Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            ))}
          </div>
        ))}
        {conversations.data?.length === 0 && <p className="px-2 py-4 text-xs text-muted-foreground">No conversations yet.</p>}
      </ScrollArea>
      <div className="border-t p-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-sidebar-accent">
              <Avatar className="size-7">
                <AvatarFallback>{(me.data?.display_name || me.data?.email || "?").slice(0, 1).toUpperCase()}</AvatarFallback>
              </Avatar>
              <span className="min-w-0 flex-1 truncate">{me.data?.display_name || me.data?.email}</span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            <div className="px-2 py-1.5 text-xs text-muted-foreground truncate">{me.data?.email}</div>
            <DropdownMenuItem onSelect={() => setUsageOpen(true)}>
              <BarChart3 className="size-4" /> Usage
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setClearOpen(true)}>
              <History className="size-4" /> Delete chats…
            </DropdownMenuItem>
            {me.data?.is_admin && (
              <DropdownMenuItem asChild>
                <Link to="/admin" onClick={onNavigate}>
                  <Shield className="size-4" /> Admin
                </Link>
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={() => void logout()}>
              <LogOut className="size-4" /> Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <UsageDialog open={usageOpen} onOpenChange={setUsageOpen} />
        <ClearHistoryDialog open={clearOpen} onOpenChange={setClearOpen} />
      </div>
    </div>
  );
}
