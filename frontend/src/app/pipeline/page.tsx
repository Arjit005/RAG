'use client';

import React, { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { IngestionJob } from '@/types';
import { PageHeader, Card, Badge } from '@/components/ui/core';
import { RefreshCw, Activity, CheckCircle2, AlertCircle, Clock } from 'lucide-react';
import { formatDate } from '@/lib/utils';

export default function PipelineMonitorPage() {
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchJobs = async () => {
    setLoading(true);
    try {
      const data = await api.listPipelineJobs(100);
      setJobs(data);
    } catch (e: any) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Pipeline Monitor"
        subtitle="Real-time observability into asynchronous document ingestion jobs, extraction stages, and vector indexing."
        actions={
          <button
            onClick={fetchJobs}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 bg-white border border-[#E2E8F0] text-[#172B4D] rounded-lg text-sm font-medium hover:bg-[#F8FAFC] disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="text-xs font-semibold text-[#64748B] uppercase">Total Tracked</div>
          <div className="text-2xl font-bold text-[#172B4D] mt-1">{jobs.length}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs font-semibold text-[#16A34A] uppercase">Completed</div>
          <div className="text-2xl font-bold text-[#16A34A] mt-1">
            {jobs.filter((j) => j.status === 'completed').length}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs font-semibold text-[#D97706] uppercase">In-flight / Processing</div>
          <div className="text-2xl font-bold text-[#D97706] mt-1">
            {jobs.filter((j) => j.status === 'processing' || j.status === 'pending').length}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs font-semibold text-[#DC2626] uppercase">Failed</div>
          <div className="text-2xl font-bold text-[#DC2626] mt-1">
            {jobs.filter((j) => j.status === 'failed').length}
          </div>
        </Card>
      </div>

      <Card className="p-0 overflow-hidden">
        <div className="p-4 border-b border-[#E2E8F0] flex items-center justify-between">
          <h2 className="text-sm font-bold text-[#172B4D]">Persisted Ingestion Jobs</h2>
          <span className="text-xs text-[#64748B]">Auto-refreshes every 10 seconds</span>
        </div>

        {jobs.length === 0 ? (
          <div className="text-center py-16 text-sm text-[#64748B]">No ingestion jobs recorded.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-xs font-semibold text-[#64748B] uppercase">
                <tr>
                  <th className="px-4 py-3">Job ID</th>
                  <th className="px-4 py-3">Document ID</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Progress</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3">Error / Note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {jobs.map((j) => (
                  <tr key={j.id} className="hover:bg-[#F8FAFC]">
                    <td className="px-4 py-3 font-mono text-xs">{j.id}</td>
                    <td className="px-4 py-3 font-mono text-xs text-[#64748B]">
                      {j.document_id ? `${j.document_id.slice(0, 8)}...` : '—'}
                    </td>
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
                    <td className="px-4 py-3 font-semibold text-xs">
                      <div className="flex items-center gap-2">
                        <div className="w-16 bg-[#E2E8F0] h-1.5 rounded-full overflow-hidden">
                          <div
                            className={`h-full ${
                              j.status === 'completed'
                                ? 'bg-[#16A34A]'
                                : j.status === 'failed'
                                ? 'bg-[#DC2626]'
                                : 'bg-[#2563EB]'
                            }`}
                            style={{ width: `${j.progress_percent}%` }}
                          />
                        </div>
                        <span>{j.progress_percent}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs text-[#64748B]">{formatDate(j.created_at)}</td>
                    <td className="px-4 py-3 text-xs text-[#DC2626] max-w-xs truncate" title={j.error_message || ''}>
                      {j.error_message || '—'}
                    </td>
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
