import { create } from 'zustand';

interface UIState {
  siderCollapsed: boolean;
  toggleSider: () => void;
  setSiderCollapsed: (collapsed: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  siderCollapsed: false,
  toggleSider: () => set((s) => ({ siderCollapsed: !s.siderCollapsed })),
  setSiderCollapsed: (collapsed) => set({ siderCollapsed: collapsed }),
}));
