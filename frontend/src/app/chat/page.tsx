'use client';

import React, { useState, useRef, useEffect } from 'react';
import { api } from '@/lib/api';
import { ChatMessage, Citation } from '@/types';
import { PageHeader, Card, Badge } from '@/components/ui/core';
import { Send, Bot, User as UserIcon, Sparkles, BookOpen, ChevronDown, ChevronRight, Sliders, Trash2 } from 'lucide-react';

const SUGGESTED_INQUIRIES = [
  'What is the self-attention mechanism and how does it compute representations?',
  'What are the key object detection findings and proposal mechanisms discussed?',
  'Explain the architecture differences between dot-product and additive attention.',
  'Summarize the supervised vs unsupervised learning fundamentals from the notes.',
];

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [topK, setTopK] = useState(5);
  const [useHybrid, setUseHybrid] = useState(true);
  const [useRerank, setUseRerank] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isStreaming]);

  const handleSend = async (queryText?: string) => {
    const text = queryText || input;
    if (!text.trim() || isStreaming) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };

    const assistantMsgId = `assistant-${Date.now()}`;
    const assistantMsg: ChatMessage = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      citations: [],
      timestamp: new Date().toISOString(),
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput('');
    setIsStreaming(true);

    try {
      await api.chatStream(
        text,
        {
          top_k: topK,
          use_hybrid: useHybrid,
          use_rerank: useRerank,
          chat_history: messages.map((m) => ({ role: m.role, content: m.content })),
        },
        {
          onModelSelected: (info) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? {
                      ...m,
                      selectedModel: info.model_id,
                      selectedProvider: info.provider,
                      failoverOccurred: info.failover_occurred,
                    }
                  : m
              )
            );
          },
          onCitations: (citations) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantMsgId ? { ...m, citations } : m))
            );
          },
          onToken: (token) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, content: m.content + token } : m
              )
            );
          },
          onComplete: () => {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantMsgId ? { ...m, isStreaming: false } : m))
            );
            setIsStreaming(false);
          },
          onError: (err) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, content: m.content ? `${m.content}\n\n[Error: ${err}]` : `Error: ${err}`, isStreaming: false }
                  : m
              )
            );
            setIsStreaming(false);
          },
        }
      );
    } catch (e: any) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? { ...m, content: `Transfer error: ${e.message}`, isStreaming: false }
            : m
        )
      );
      setIsStreaming(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)] max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 mb-4 border-b border-[#E2E8F0]">
        <div>
          <h1 className="text-2xl font-bold text-[#172B4D]">AI Research Workspace</h1>
          <p className="text-sm text-[#64748B]">
            Evidence-grounded multi-modal intelligence across enterprise documents.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-[#E2E8F0] rounded-lg bg-white hover:bg-[#F8FAFC] text-[#172B4D]"
          >
            <Sliders className="w-3.5 h-3.5" />
            Parameters
          </button>
          <button
            onClick={clearChat}
            disabled={messages.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-[#E2E8F0] rounded-lg bg-white hover:bg-[#F8FAFC] text-[#DC2626] disabled:opacity-50"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear
          </button>
        </div>
      </div>

      {/* Settings Bar */}
      {showSettings && (
        <Card className="mb-4 bg-[#F8FAFC] p-4 text-xs space-y-3">
          <div className="font-semibold text-[#172B4D]">Retrieval Parameters & Session Controls</div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-[#64748B] mb-1 font-medium">Top-K Chunks: {topK}</label>
              <input
                type="range"
                min="1"
                max="10"
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                className="w-full"
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="hybrid"
                checked={useHybrid}
                onChange={(e) => setUseHybrid(e.target.checked)}
                className="rounded text-[#2563EB]"
              />
              <label htmlFor="hybrid" className="text-[#172B4D] font-medium">
                Hybrid Search (Dense + BM25)
              </label>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="rerank"
                checked={useRerank}
                onChange={(e) => setUseRerank(e.target.checked)}
                className="rounded text-[#2563EB]"
              />
              <label htmlFor="rerank" className="text-[#172B4D] font-medium">
                FlashRank Reranking
              </label>
            </div>
          </div>
        </Card>
      )}

      {/* Chat Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {messages.length === 0 ? (
          <div className="text-center py-16 space-y-4">
            <div className="w-12 h-12 rounded-full bg-[#E0F2FE] text-[#2563EB] flex items-center justify-center mx-auto text-2xl">
              💬
            </div>
            <div>
              <h2 className="text-lg font-bold text-[#172B4D]">Start an AI Research Inquiry</h2>
              <p className="text-sm text-[#64748B] max-w-md mx-auto mt-1">
                Submit an inquiry across indexed documents. Responses are synthesized in real time with
                verbatim citations.
              </p>
            </div>

            <div className="pt-6 max-w-xl mx-auto">
              <div className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">
                Suggested Research Inquiries
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-left">
                {SUGGESTED_INQUIRIES.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(q)}
                    className="p-3 text-xs bg-white border border-[#E2E8F0] hover:border-[#2563EB] hover:bg-[#F8FAFC] rounded-lg text-[#172B4D] transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {m.role === 'assistant' && (
                <div className="w-8 h-8 rounded-full bg-[#2563EB] text-white flex items-center justify-center flex-shrink-0 text-sm">
                  <Bot className="w-4 h-4" />
                </div>
              )}
              <div
                className={`max-w-2xl rounded-xl p-4 text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-[#2563EB] text-white'
                    : 'bg-white border border-[#E2E8F0] text-[#172B4D]'
                }`}
              >
                {/* Model Routing / Failover Indicator Pill */}
                {m.role === 'assistant' && (m.selectedModel || m.failoverOccurred) && (
                  <div className="mb-2 pb-2 border-b border-[#E2E8F0] flex items-center gap-2">
                    <span className="text-[11px] font-medium text-[#64748B]">Routed via:</span>
                    <span className="text-[11px] font-semibold text-[#172B4D] bg-[#F1F5F9] px-2 py-0.5 rounded">
                      {m.selectedModel} ({m.selectedProvider?.toUpperCase()})
                    </span>
                    {m.failoverOccurred && (
                      <span className="text-[10px] font-bold text-[#D97706] bg-[#FEF3C7] border border-[#FDE68A] px-1.5 py-0.5 rounded">
                        ⚡ Auto-failover
                      </span>
                    )}
                  </div>
                )}

                <div className="whitespace-pre-wrap">
                  {m.content}
                  {m.isStreaming && <span className="inline-block w-2 h-4 bg-[#2563EB] animate-pulse ml-1">▌</span>}
                </div>

                {/* Citations Drawer */}
                {m.citations && m.citations.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-[#E2E8F0]">
                    <div className="text-xs font-semibold text-[#64748B] mb-2 flex items-center gap-1.5">
                      <BookOpen className="w-3.5 h-3.5" />
                      Verified Evidence & Citations ({m.citations.length} sources)
                    </div>
                    <div className="space-y-2">
                      {m.citations.map((c, i) => (
                        <div
                          key={i}
                          className="p-2.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg text-xs space-y-1"
                        >
                          <div className="flex items-center justify-between font-medium">
                            <span className="text-[#172B4D]">📄 {c.source} (Page {c.page})</span>
                            <span className="text-[#64748B]">Score: {c.distance?.toFixed(4)}</span>
                          </div>
                          <p className="text-[#475569] italic">"{c.snippet}"</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              {m.role === 'user' && (
                <div className="w-8 h-8 rounded-full bg-[#E2E8F0] text-[#172B4D] flex items-center justify-center flex-shrink-0 text-sm">
                  <UserIcon className="w-4 h-4" />
                </div>
              )}
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Box */}
      <div className="pt-4 border-t border-[#E2E8F0]">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question across your indexed documents..."
            disabled={isStreaming}
            className="flex-1 px-4 py-3 bg-white border border-[#CBD5E1] rounded-xl text-sm focus:outline-none focus:border-[#2563EB] disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className="px-5 py-3 bg-[#2563EB] hover:bg-[#1D4ED8] text-white rounded-xl text-sm font-semibold flex items-center gap-2 disabled:opacity-50 transition-colors cursor-pointer"
          >
            <Send className="w-4 h-4" />
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
