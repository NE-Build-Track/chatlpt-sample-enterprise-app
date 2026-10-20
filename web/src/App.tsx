import { createBrowserRouter } from "react-router";
import { ChatLayout } from "@/features/chat/ChatLayout";
import { ChatPage } from "@/features/chat/ChatPage";
import { EmptyChat } from "@/features/chat/EmptyChat";
import { LoginPage } from "@/features/auth/LoginPage";
import { SignupPage } from "@/features/auth/SignupPage";
import { ClaimPage } from "@/features/auth/ClaimPage";
import { AdminPage } from "@/features/admin/AdminPage";
import { RequireUser } from "@/features/auth/RequireUser";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/signup", element: <SignupPage /> },
  { path: "/claim", element: <ClaimPage /> },
  {
    path: "/",
    element: (
      <RequireUser>
        <ChatLayout />
      </RequireUser>
    ),
    children: [
      { index: true, element: <EmptyChat /> },
      { path: "c/:conversationId", element: <ChatPage /> },
      { path: "admin", element: <AdminPage /> },
    ],
  },
]);
