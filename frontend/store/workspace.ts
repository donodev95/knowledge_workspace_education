"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";
export type Conversation = { id: string; title: string };
export type Message = {
  id: string;
  role: string;
  content: string;
  sources?: { document_name?: string; page_number?: number | null }[];
};
export type Paper = { id: string; code: string; title: string };
type State = {
  session: { email: string; token: string; expiresAt: number } | null;
  conversations: Conversation[];
  activeId: string | null;
  messages: Record<string, Message[]>;
  papers: Paper[];
  selectedPaperId: string;
  signIn: (email: string, token: string, expiresIn: number) => void;
  logout: () => void;
  setConversations: (items: Conversation[]) => void;
  selectConversation: (id: string | null) => void;
  setMessages: (id: string, items: Message[]) => void;
  setPapers: (items: Paper[]) => void;
  selectPaper: (id: string) => void;
};
const empty = {
  session: null,
  conversations: [],
  activeId: null,
  messages: {},
  papers: [],
  selectedPaperId: "",
};
export const useWorkspace = create<State>()(
  persist(
    (set) => ({
      ...empty,
      signIn: (email, token, expiresIn) =>
        set({
          ...empty,
          session: { email, token, expiresAt: Date.now() + expiresIn * 1000 },
        }),
      logout: () => set(empty),
      setConversations: (conversations) => set({ conversations }),
      selectConversation: (activeId) => set({ activeId }),
      setMessages: (id, items) =>
        set((s) => ({ messages: { ...s.messages, [id]: items } })),
      setPapers: (papers) => set({ papers }),
      selectPaper: (selectedPaperId) => set({ selectedPaperId }),
    }),
    {
      name: "knowledge-session",
      partialize: (s) => ({ session: s.session }),
      skipHydration: true,
    },
  ),
);
