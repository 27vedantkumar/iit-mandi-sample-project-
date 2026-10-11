import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  MessageSquareText,
  Network,
  FolderTree,
  CheckSquare,
  Calendar,
  Layers,
  GraduationCap,
  Terminal,
  Gamepad2
} from 'lucide-react';

export const Sidebar = () => {
  const location = useLocation();

  const navItems = [
    { path: '/dashboard', alias: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/tutor', label: 'Grounded Tutor', icon: MessageSquareText, badge: '6 Modes' },
    { path: '/graph', label: 'Knowledge Graph', icon: Network },
    { path: '/sources', label: 'Source Explorer', icon: FolderTree },
    { path: '/assessment', label: 'Adaptive Assessment', icon: CheckSquare, badge: 'Diagnostic' },
    { path: '/planner', label: 'Study Planner', icon: Calendar, badge: 'Blitz' },
    { path: '/flashcards', label: 'Flashcards', icon: Layers, badge: 'SM-2' },
    { path: '/exams', label: 'Exam Simulator', icon: GraduationCap },
    { path: '/coding', label: 'Coding Lab', icon: Terminal },
    { path: '/games', label: 'Mini-Games', icon: Gamepad2, badge: '3 Games' },
  ];

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-950/50 flex flex-col justify-between p-4 shrink-0 h-[calc(100vh-4rem)] sticky top-16">
      <div className="space-y-1">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 px-3 mb-2 block">
          Learning Intelligence
        </span>

        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive =
            location.pathname === item.path ||
            (item.alias && location.pathname === item.alias) ||
            (item.path !== '/' && item.path !== '/dashboard' && location.pathname.startsWith(item.path));

          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-medium transition-all ${
                isActive
                  ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
              }`}
            >
              <div className="flex items-center gap-3">
                <Icon className={`w-4 h-4 ${isActive ? 'text-indigo-400' : 'text-slate-500'}`} />
                <span>{item.label}</span>
              </div>

              {item.badge && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-semibold ${
                  isActive ? 'bg-indigo-500/20 text-indigo-300' : 'bg-slate-800 text-slate-400'
                }`}>
                  {item.badge}
                </span>
              )}
            </NavLink>
          );
        })}
      </div>

      <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80 text-[11px] text-slate-400 space-y-1">
        <div className="font-semibold text-slate-300 flex items-center justify-between">
          <span>Source Grounding</span>
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
        </div>
        <p className="text-[10px] text-slate-400 leading-relaxed">
          Zero-hallucination verification active. All outputs grounded in course PDFs, slides, and video transcripts.
        </p>
      </div>
    </aside>
  );
};

