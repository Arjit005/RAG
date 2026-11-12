'use client';

import React, { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { IngestionJob, DocumentItem } from '@/types';
import { PageHeader, Card, Badge } from '@/components/ui/core';
import { ClipboardList, Shield, RefreshCw } from 'lucide-react';
import { formatDate } from '@/lib/utils';

export default function AuditPage() {
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [j, d] = await Promise.all([api.listPipelineJobs(50), api.listDocuments()]);
      setJobs(j);
      setDocs(d);
    } catch (e: any) {
      console.error(e);
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
        title="Activity & Audit"
        subtitle="Security audit trail and operational log of tenant actions, document lifecycle changes, and ingestion pipelines."
        actions={
          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 bg-white border border-[#E2E8F0] text-[#172B4D] rounded-lg text-sm font-medium hover:bg-[#F8FAFC] disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh Audit
          </button>
        }
      />

      <Card className="p-0 overflow-hidden">
        <div className="p-4 border-b border-[#E2E8F0] flex items-center justify-between">
          <h2 className="text-sm font-bold text-[#172B4D]">Operational Audit Records</h2>
          <span className="text-xs text-[#64748B]">Scoped to authorized tenant</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-xs font-semibold text-[#64748B] uppercase">
              <tr>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Event Type</th>
                <th className="px-4 py-3">Resource Target</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actor / Tenant</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E2E8F0]">
              {docs.map((d) => (
                <tr key={d.id} className="hover:bg-[#F8FAFC]">
                  <td className="px-4 py-3 text-xs text-[#64748B]">{formatDate(d.created_at)}</td>
                  <td className="px-4 py-3 font-semibold text-xs text-[#172B4D]">DOCUMENT_INDEXED</td>
                  <td className="px-4 py-3 text-xs font-mono">{d.filename}</td>
                  <td className="px-4 py-3">
                    <Badge type="success">COMPLETED</Badge>
                  </td>
                  <td className="px-4 py-3 text-xs text-[#64748B]">{d.tenant_id}</td>
                </tr>
              ))}
              {jobs.map((j) => (
                <tr key={j.id} className="hover:bg-[#F8FAFC]">
                  <td className="px-4 py-3 text-xs text-[#64748B]">{formatDate(j.created_at)}</td>
                  <td className="px-4 py-3 font-semibold text-xs text-[#172B4D]">INGESTION_JOB</td>
                  <td className="px-4 py-3 text-xs font-mono">{j.id}</td>
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
                  <td className="px-4 py-3 text-xs text-[#64748B]">{j.tenant_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
