'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import {
  LayoutDashboard,
  MessageSquare,
  BookOpen,
  Search,
  Activity,
  HeartPulse,
  ClipboardList,
  Settings,
  ChevronRight,
  Shield,
  Zap,
  LogOut,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const navWorkspace = [
  { name: 'Overview', href: '/', icon: LayoutDashboard },
  { name: 'Research Chat', href: '/chat', icon: MessageSquare },
  { name: 'Knowledge Base', href: '/documents', icon: BookOpen },
  { name: 'Retrieval Explorer', href: '/retrieval', icon: Search },
  { name: 'Pipeline Monitor', href: '/pipeline', icon: Activity },
];

const navOperations = [
  { name: 'System Health', href: '/health', icon: HeartPulse },
  { name: 'Activity & Audit', href: '/audit', icon: ClipboardList },
  { name: 'Settings', href: '/settings', icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await api.logout();
      router.push('/login');
      router.refresh();
    } catch {
      window.location.href = '/login';
    }
  };

  return (
    <aside className="w-64 bg-[#F1F5F9] border-r border-[#E2E8F0] flex flex-col h-screen fixed left-0 top-0 z-30 select-none">
      {/* Brand Header */}
      <div className="p-5 border-b border-[#E2E8F0] flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-[#2563EB] text-white flex items-center justify-center font-bold text-lg shadow-xs">
          ⚡
        </div>
        <div>
          <div className="font-bold text-[#172B4D] text-base leading-tight">RAG Intelligence</div>
          <div className="text-xs text-[#64748B] font-medium">Enterprise SaaS Platform</div>
        </div>
      </div>

      {/* Nav Menu */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        <div>
          <div className="px-3 mb-2 text-[11px] font-bold uppercase tracking-wider text-[#94A3B8]">
            Workspace
          </div>
          <nav className="space-y-1">
            {navWorkspace.map((item) => {
              const active = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                    active
                      ? 'bg-[#2563EB] text-white shadow-xs'
                      : 'text-[#172B4D] hover:bg-[#E2E8F0] hover:text-[#0F172A]'
                  )}
                >
                  <Icon className={cn('w-4 h-4', active ? 'text-white' : 'text-[#64748B]')} />
                  <span>{item.name}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        <div>
          <div className="px-3 mb-2 text-[11px] font-bold uppercase tracking-wider text-[#94A3B8]">
            Operations
          </div>
          <nav className="space-y-1">
            {navOperations.map((item) => {
              const active = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                    active
                      ? 'bg-[#2563EB] text-white shadow-xs'
                      : 'text-[#172B4D] hover:bg-[#E2E8F0] hover:text-[#0F172A]'
                  )}
                >
                  <Icon className={cn('w-4 h-4', active ? 'text-white' : 'text-[#64748B]')} />
                  <span>{item.name}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Footer Info & Logout */}
      <div className="p-4 border-t border-[#E2E8F0] bg-white text-xs text-[#64748B] space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-[#172B4D]">Tenant:</span>
          <span className="px-1.5 py-0.5 bg-[#F1F5F9] rounded text-[11px] font-mono">default-tenant</span>
        </div>
        <div className="flex items-center justify-between">
          <span>Env:</span>
          <span className="text-[#16A34A] font-medium flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#16A34A]"></span> Production
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span>Cluster:</span>
          <span className="truncate max-w-[110px]" title="Neon AWS us-east-2">Neon us-east-2</span>
        </div>
        <button
          onClick={handleLogout}
          className="w-full mt-2 pt-2 border-t border-[#F1F5F9] flex items-center justify-center gap-2 py-2 px-3 bg-[#FEF2F2] hover:bg-[#FEE2E2] text-[#DC2626] rounded-lg font-medium transition-colors cursor-pointer"
        >
          <LogOut className="w-3.5 h-3.5" />
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  );
}
