'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { MetricsSummary, IngestionJob, DocumentItem } from '@/types';
import { PageHeader, MetricCard, Card, Badge } from '@/components/ui/core';
import { FileText, Layers, Database, Cpu, RefreshCw, AlertCircle, CheckCircle2, Clock } from 'lucide-react';
import { formatDate } from '@/lib/utils';

export default function OverviewPage() {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [m, j, d] = await Promise.all([
        api.getMetricsSummary(),
        api.listPipelineJobs(5),
        api.listDocuments(undefined, 5),
      ]);
      setMetrics(m);
      setJobs(j);
      setDocs(d);
    } catch (e: any) {
      setError(e.message || 'Failed to load overview data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview Dashboard"
        subtitle="Operational metrics, storage status, and document inventory."
        actions={
          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 bg-white border border-[#E2E8F0] text-[#172B4D] rounded-lg text-sm font-medium hover:bg-[#F8FAFC] disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        }
      />

      {error && (
        <div className="p-4 bg-[#FEE2E2] border border-[#FECACA] rounded-xl flex items-center gap-3 text-[#DC2626] text-sm">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* KPI Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Total Documents"
          value={loading ? '...' : (metrics?.total_documents ?? 0)}
          subtitle="Neon PostgreSQL"
          badgeText="100% Synced"
          badgeType="success"
          icon={<FileText className="w-6 h-6" />}
        />
        <MetricCard
          label="Document Chunks"
          value={loading ? '...' : (metrics?.total_chunks ?? 0)}
          subtitle="Qdrant Vector DB"
          badgeText="Active"
          badgeType="info"
          icon={<Layers className="w-6 h-6" />}
        />
        <MetricCard
          label="Tenants"
          value="1"
          subtitle="default-tenant"
          badgeText="Isolated"
          badgeType="neutral"
          icon={<Database className="w-6 h-6" />}
        />
        <MetricCard
          label="Active Ingestion"
          value={loading ? '...' : (metrics?.active_jobs_count ?? 0)}
          subtitle="Ingestion Jobs"
          badgeText={metrics?.active_jobs_count === 0 ? 'Idle' : 'Running'}
          badgeType={metrics?.active_jobs_count === 0 ? 'neutral' : 'warning'}
          icon={<Cpu className="w-6 h-6" />}
        />
      </div>

      {/* System Infrastructure Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <h2 className="text-base font-bold text-[#172B4D] mb-4">System Infrastructure</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg">
              <div className="text-xs font-semibold uppercase text-[#64748B]">Relational Storage</div>
              <div className="text-sm font-bold text-[#172B4D] mt-1">{metrics?.storage_provider || 'PostgreSQL'}</div>
              <div className="text-xs text-[#16A34A] flex items-center gap-1 mt-2">
                <CheckCircle2 className="w-3.5 h-3.5" /> Connected
              </div>
            </div>
            <div className="p-4 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg">
              <div className="text-xs font-semibold uppercase text-[#64748B]">Vector Engine</div>
              <div className="text-sm font-bold text-[#172B4D] mt-1 truncate" title={metrics?.vector_engine}>
                {metrics?.vector_engine || 'Qdrant Store'}
              </div>
              <div className="text-xs text-[#16A34A] flex items-center gap-1 mt-2">
                <CheckCircle2 className="w-3.5 h-3.5" /> Vectors Ready
              </div>
            </div>
            <div className="p-4 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg">
              <div className="text-xs font-semibold uppercase text-[#64748B]">FastAPI Gateway</div>
              <div className="text-sm font-bold text-[#172B4D] mt-1">REST + SSE Gateway</div>
              <div className="text-xs text-[#16A34A] flex items-center gap-1 mt-2">
                <CheckCircle2 className="w-3.5 h-3.5" /> Port 8000 Ready
              </div>
            </div>
          </div>
        </Card>

        <Card>
          <h2 className="text-base font-bold text-[#172B4D] mb-4">Pipeline Status</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-[#64748B]">Pending / In-flight:</span>
              <span className="font-semibold text-[#172B4D]">{metrics?.active_jobs_count ?? 0}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-[#64748B]">Recent Completed:</span>
              <span className="font-semibold text-[#16A34A]">
                {jobs.filter((j) => j.status === 'completed').length}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-[#64748B]">Recent Failed:</span>
              <span className="font-semibold text-[#DC2626]">
                {jobs.filter((j) => j.status === 'failed').length}
              </span>
            </div>
          </div>
        </Card>
      </div>

      {/* Recent Ingestion Activity */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-bold text-[#172B4D]">Recent Ingestion Activity</h2>
        </div>
        {jobs.length === 0 ? (
          <div className="text-center py-8 text-sm text-[#64748B]">No recent ingestion jobs found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-xs font-semibold text-[#64748B] uppercase">
                <tr>
                  <th className="px-4 py-3">Job ID</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Progress</th>
                  <th className="px-4 py-3">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {jobs.map((j) => (
                  <tr key={j.id} className="hover:bg-[#F8FAFC]">
                    <td className="px-4 py-3 font-mono text-xs">{j.id}</td>
                    <td className="px-4 py-3">
                      <Badge
                        type={
                          j.status === 'completed'
                            ? 'success'
                            : j.status === 'failed'
                            ? 'error'
                            : 'warning'
                        }
                      >
                        {j.status.toUpperCase()}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">{j.progress_percent}%</td>
                    <td className="px-4 py-3 text-xs text-[#64748B]">{formatDate(j.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
