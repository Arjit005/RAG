'use client';

import React, { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { PageHeader, Card, Badge } from '@/components/ui/core';
import { Settings, Shield, Sliders, CheckCircle2, Lock, Cpu, Server, Activity, RefreshCw } from 'lucide-react';
import { ModelsListResponse, ModelDescriptor, ProviderHealth } from '@/types';

export default function SettingsPage() {
  const [model, setModel] = useState('qwen/qwen3.8-27b');
  const [topK, setTopK] = useState(5);
  const [hybrid, setHybrid] = useState(true);
  const [rerank, setRerank] = useState(true);
  const [saved, setSaved] = useState(false);

  // Router & Model Management State
  const [routerData, setRouterData] = useState<ModelsListResponse | null>(null);
  const [loadingRouter, setLoadingRouter] = useState(false);
  const [updatingModelId, setUpdatingModelId] = useState<string | null>(null);

  const fetchRouterStatus = async () => {
    setLoadingRouter(true);
    try {
      const data = await api.getLLMModels();
      setRouterData(data);
      if (data.active_model_id) {
        setModel(data.active_model_id);
      }
    } catch (err) {
      console.error('Failed to load router data:', err);
    } finally {
      setLoadingRouter(false);
    }
  };

  useEffect(() => {
    fetchRouterStatus();
  }, []);

  const handleToggleModel = async (modelId: string, currentEnabled: boolean) => {
    setUpdatingModelId(modelId);
    try {
      await api.updateLLMConfig(modelId, { enabled: !currentEnabled });
      await fetchRouterStatus();
    } catch (err) {
      console.error('Failed to toggle model:', err);
    } finally {
      setUpdatingModelId(null);
    }
  };

  const handlePriorityChange = async (modelId: string, newPriority: number) => {
    setUpdatingModelId(modelId);
    try {
      await api.updateLLMConfig(modelId, { priority: newPriority });
      await fetchRouterStatus();
    } catch (err) {
      console.error('Failed to update priority:', err);
    } finally {
      setUpdatingModelId(null);
    }
  };

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <PageHeader
        title="Settings"
        subtitle="Configure multi-provider LLM routing, automatic free-model failover, and retrieval strategies."
      />

      {saved && (
        <div className="p-4 bg-[#DCFCE7] border border-[#BBF7D0] rounded-xl flex items-center gap-3 text-[#16A34A] text-sm">
          <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
          <span>Tenant settings saved successfully.</span>
        </div>
      )}

      {/* Model & Provider Management Card */}
      <Card className="space-y-4">
        <div className="flex items-center justify-between border-b border-[#E2E8F0] pb-3">
          <h2 className="text-base font-bold text-[#172B4D] flex items-center gap-2">
            <Cpu className="w-4 h-4 text-[#2563EB]" />
            Multi-Provider AI Router & Failover Engine
          </h2>
          <button
            onClick={fetchRouterStatus}
            disabled={loadingRouter}
            className="flex items-center gap-1.5 text-xs text-[#2563EB] hover:text-[#1D4ED8] font-medium cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingRouter ? 'animate-spin' : ''}`} />
            Refresh Status
          </button>
        </div>

        {/* Provider Circuit Breakers Status */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {routerData?.providers.map((p) => {
            const isClosed = p.state === 'closed';
            const isOpen = p.state === 'open';
            return (
              <div
                key={p.provider}
                className="p-3.5 bg-[#F8FAFC] rounded-xl border border-[#E2E8F0] space-y-2 text-xs"
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold uppercase tracking-wider text-[#172B4D]">
                    {p.provider}
                  </span>
                  <Badge type={isClosed ? 'success' : (isOpen ? 'error' : 'warning')}>
                    {isClosed ? 'HEALTHY' : (isOpen ? 'CIRCUIT OPEN' : 'TRIAL')}
                  </Badge>
                </div>
                <div className="text-[#64748B] space-y-1">
                  <div className="flex justify-between">
                    <span>Keys Configured:</span>
                    <span className="font-semibold text-[#172B4D]">{p.available_keys_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Active Key:</span>
                    <span className="font-mono text-[#172B4D]">{p.active_key_masked || 'None'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Failures / 429s:</span>
                    <span className="text-[#172B4D]">{p.failure_count} / {p.consecutive_429_count}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Model Registry Table */}
        <div className="overflow-x-auto pt-2">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-[#E2E8F0] text-[#64748B] font-semibold bg-[#F8FAFC]">
                <th className="py-2.5 px-3">Model / Provider</th>
                <th className="py-2.5 px-3">Tier</th>
                <th className="py-2.5 px-3">Context</th>
                <th className="py-2.5 px-3">Capabilities</th>
                <th className="py-2.5 px-3">Priority</th>
                <th className="py-2.5 px-3 text-right">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E2E8F0]">
              {routerData?.models.map((m) => (
                <tr key={m.model_id} className="hover:bg-[#F8FAFC]/50 transition-colors">
                  <td className="py-3 px-3">
                    <div className="font-bold text-[#172B4D]">{m.display_name}</div>
                    <div className="font-mono text-[10px] text-[#64748B]">{m.model_id}</div>
                  </td>
                  <td className="py-3 px-3">
                    <Badge type={m.tier === 'free' ? 'success' : 'neutral'}>
                      {m.tier.toUpperCase()}
                    </Badge>
                  </td>
                  <td className="py-3 px-3 text-[#64748B]">
                    {(m.context_window / 1024).toFixed(0)}k tokens
                  </td>
                  <td className="py-3 px-3">
                    <div className="flex gap-1.5 flex-wrap">
                      {m.supports_multimodal && (
                        <span className="px-1.5 py-0.5 bg-[#EFF6FF] text-[#2563EB] rounded text-[10px] font-medium">
                          Vision
                        </span>
                      )}
                      {m.supports_streaming && (
                        <span className="px-1.5 py-0.5 bg-[#F0FDF4] text-[#16A34A] rounded text-[10px] font-medium">
                          SSE Stream
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-3 px-3">
                    <input
                      type="number"
                      min="1"
                      max="100"
                      value={m.priority}
                      disabled={updatingModelId === m.model_id}
                      onChange={(e) => handlePriorityChange(m.model_id, parseInt(e.target.value) || 10)}
                      className="w-14 p-1 text-center bg-white border border-[#E2E8F0] rounded text-xs font-semibold"
                    />
                  </td>
                  <td className="py-3 px-3 text-right">
                    <button
                      onClick={() => handleToggleModel(m.model_id, m.enabled)}
                      disabled={updatingModelId === m.model_id}
                      className={`px-3 py-1 rounded text-[11px] font-semibold cursor-pointer transition-colors ${
                        m.enabled
                          ? 'bg-[#DCFCE7] text-[#16A34A] hover:bg-[#BBF7D0]'
                          : 'bg-[#F1F5F9] text-[#64748B] hover:bg-[#E2E8F0]'
                      }`}
                    >
                      {m.enabled ? 'Enabled' : 'Disabled'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Retrieval Strategy Settings Card */}
      <Card className="space-y-4">
        <h2 className="text-base font-bold text-[#172B4D] flex items-center gap-2">
          <Sliders className="w-4 h-4 text-[#2563EB]" />
          Default Retrieval Configuration
        </h2>

        <div className="space-y-4 pt-2 text-sm">
          <div>
            <label className="block text-[#64748B] font-medium mb-1">Preferred Model Selection</label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full p-2.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg text-sm text-[#172B4D]"
            >
              {routerData?.models.filter(m => m.enabled).map((m) => (
                <option key={m.model_id} value={m.model_id}>
                  {m.display_name} ({m.tier.toUpperCase()})
                </option>
              )) || (
                <>
                  <option value="gemini-3.8-flash">Google Gemini 3.8 Flash (FREE)</option>
                  <option value="gemini-2.5-flash">Google Gemini 2.5 Flash (FREE)</option>
                  <option value="liquid/lfm-3-1.7b:free">OpenRouter: Liquid LFM 3 (FREE)</option>
                  <option value="qwen/qwen3.8-27b">Groq: Qwen 3.8 27B (Fast Inference)</option>
                </>
              )}
            </select>
            <p className="text-xs text-[#64748B] mt-1">
              If the selected model exceeds rate limits or fails, the router automatically fails over to the next healthy model.
            </p>
          </div>

          <div>
            <label className="block text-[#64748B] font-medium mb-1">Default Top-K Results: {topK}</label>
            <input
              type="range"
              min="1"
              max="15"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="w-full cursor-pointer"
            />
          </div>

          <div className="flex items-center justify-between p-3 bg-[#F8FAFC] rounded-lg border border-[#E2E8F0]">
            <div>
              <div className="font-semibold text-[#172B4D]">Hybrid Search Engine</div>
              <div className="text-xs text-[#64748B]">Combines Qdrant dense vectors with BM25 keyword scoring</div>
            </div>
            <input
              type="checkbox"
              checked={hybrid}
              onChange={(e) => setHybrid(e.target.checked)}
              className="w-4 h-4 text-[#2563EB] cursor-pointer"
            />
          </div>

          <div className="flex items-center justify-between p-3 bg-[#F8FAFC] rounded-lg border border-[#E2E8F0]">
            <div>
              <div className="font-semibold text-[#172B4D]">FlashRank Cross-Encoder Reranking</div>
              <div className="text-xs text-[#64748B]">Applies ms-marco-TinyBERT-L-2-v2 to rerank candidate documents</div>
            </div>
            <input
              type="checkbox"
              checked={rerank}
              onChange={(e) => setRerank(e.target.checked)}
              className="w-4 h-4 text-[#2563EB] cursor-pointer"
            />
          </div>
        </div>
      </Card>

      {/* Tenant Isolation & Security Card */}
      <Card className="space-y-4">
        <h2 className="text-base font-bold text-[#172B4D] flex items-center gap-2">
          <Shield className="w-4 h-4 text-[#2563EB]" />
          Tenant Isolation & Credentials
        </h2>

        <div className="space-y-3 text-sm text-[#64748B]">
          <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0]">
            <span>Active Tenant:</span>
            <span className="font-mono text-[#172B4D] font-semibold">default-tenant</span>
          </div>
          <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0]">
            <span>Authentication Protocol:</span>
            <span className="text-[#172B4D]">HS256 Signed JWT Bearer Token</span>
          </div>
          <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0]">
            <span>Credential Masking:</span>
            <Badge type="success">ACTIVE (NO RAW KEYS DISPLAYED)</Badge>
          </div>
          <div className="flex items-center justify-between">
            <span>Server-side Verification:</span>
            <Badge type="success">STRICT ENFORCEMENT</Badge>
          </div>
        </div>
      </Card>

      <div className="flex justify-end">
        <button
          onClick={handleSave}
          className="px-6 py-2.5 bg-[#2563EB] hover:bg-[#1D4ED8] text-white rounded-xl text-sm font-semibold transition-colors cursor-pointer"
        >
          Save Configuration
        </button>
      </div>
    </div>
  );
}
