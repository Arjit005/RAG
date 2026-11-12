'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { Shield, Lock, Mail, ArrowRight, AlertCircle, Sparkles, CheckCircle2 } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please provide both email and password.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      await api.login(email.trim(), password);
      router.push('/');
      router.refresh();
    } catch (err: any) {
      setError(err.message || 'Invalid email or password.');
    } finally {
      setLoading(false);
    }
  };

  const fillDemoCredentials = () => {
    setEmail('admin@enterprise.internal');
    setPassword('EnterpriseAdmin2026!');
    setError(null);
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col justify-center items-center p-4">
      <div className="w-full max-w-md">
        {/* Brand Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-[#2563EB] text-white shadow-lg shadow-blue-500/20 mb-4">
            <Shield className="w-7 h-7" />
          </div>
          <h1 className="text-2xl font-bold text-[#0F172A] tracking-tight">RAG Intelligence</h1>
          <p className="text-sm text-[#64748B] mt-1 font-medium">Enterprise Multimodal Research Platform</p>
        </div>

        {/* Login Card */}
        <div className="bg-white rounded-2xl border border-[#E2E8F0] shadow-sm p-8">
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-[#0F172A]">Welcome back</h2>
            <p className="text-sm text-[#64748B]">Sign in to access evidence-grounded research workspaces.</p>
          </div>

          {error && (
            <div className="mb-6 p-3.5 bg-[#FEF2F2] border border-[#FCA5A5] rounded-xl flex items-start gap-3 text-sm text-[#991B1B]">
              <AlertCircle className="w-5 h-5 shrink-0 text-[#DC2626] mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-[#334155] uppercase tracking-wider mb-1.5">
                Email Address
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-[#94A3B8] absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@enterprise.internal"
                  required
                  className="w-full pl-10 pr-3.5 py-2.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl text-sm text-[#0F172A] placeholder-[#94A3B8] focus:outline-none focus:ring-2 focus:ring-[#2563EB]/20 focus:border-[#2563EB] transition-all"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-[#334155] uppercase tracking-wider mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-[#94A3B8] absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                  className="w-full pl-10 pr-3.5 py-2.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl text-sm text-[#0F172A] placeholder-[#94A3B8] focus:outline-none focus:ring-2 focus:ring-[#2563EB]/20 focus:border-[#2563EB] transition-all"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-2.5 px-4 bg-[#2563EB] hover:bg-[#1D4ED8] text-white font-medium text-sm rounded-xl transition-colors shadow-sm flex items-center justify-center gap-2 disabled:opacity-60 cursor-pointer"
            >
              {loading ? (
                <span>Authenticating...</span>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          {/* Quick Demo Credentials Box */}
          <div className="mt-6 pt-6 border-t border-[#F1F5F9]">
            <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-[#1E293B]">
                  <Sparkles className="w-3.5 h-3.5 text-[#2563EB]" />
                  <span>Portfolio Demo Access</span>
                </div>
                <button
                  type="button"
                  onClick={fillDemoCredentials}
                  className="text-xs font-medium text-[#2563EB] hover:underline cursor-pointer"
                >
                  Auto-fill
                </button>
              </div>
              <p className="text-xs text-[#64748B] mb-2 leading-relaxed">
                Use the pre-configured demo account to evaluate document ingestion, multi-provider model routing, and vector search.
              </p>
              <div className="space-y-1 text-xs font-mono text-[#475569] bg-white p-2.5 rounded-lg border border-[#E2E8F0]">
                <div>Email: <span className="text-[#0F172A] font-semibold">admin@enterprise.internal</span></div>
                <div>Pass:  <span className="text-[#0F172A] font-semibold">EnterpriseAdmin2026!</span></div>
              </div>
            </div>
          </div>
        </div>

        {/* Security badge footer */}
        <div className="mt-8 text-center text-xs text-[#94A3B8] flex items-center justify-center gap-2">
          <CheckCircle2 className="w-3.5 h-3.5 text-[#16A34A]" />
          <span>Stateless JWT & HttpOnly Session Protected</span>
        </div>
      </div>
    </div>
  );
}
