'use client';

import React, { useState, useEffect, useRef } from 'react';
import { api } from '@/lib/api';
import { DocumentItem, DocumentChunk } from '@/types';
import { PageHeader, Card, Badge } from '@/components/ui/core';
import {
  UploadCloud,
  FileText,
  Search,
  RefreshCw,
  Trash2,
  X,
  Layers,
  CheckCircle2,
  AlertCircle,
  FileUp,
} from 'lucide-react';
import { formatBytes, formatDate } from '@/lib/utils';

interface StagedFile {
  file: File;
  id: string;
}

export default function KnowledgeBasePage() {
  const [activeTab, setActiveTab] = useState<'inventory' | 'inspector' | 'upload'>('inventory');
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Drag & drop upload state
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number; message: string } | null>(null);
  const [uploadResults, setUploadResults] = useState<{ filename: string; status: 'success' | 'error'; message: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocs = async () => {
    try {
      setLoading(true);
      const data = await api.listDocuments(searchQuery);
      setDocs(data);
      if (data.length > 0 && !selectedDocId) {
        setSelectedDocId(data[0].id);
      }
    } catch (e: any) {
      setError(e.message || 'Failed to fetch documents');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocs();
  }, [searchQuery]);

  useEffect(() => {
    if (selectedDocId) {
      const loadDocDetails = async () => {
        try {
          const [d, c] = await Promise.all([
            api.getDocument(selectedDocId),
            api.getDocumentChunks(selectedDocId),
          ]);
          setSelectedDoc(d);
          setChunks(c);
        } catch (e: any) {
          console.error(e);
        }
      };
      loadDocDetails();
    }
  }, [selectedDocId]);

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(Array.from(e.target.files));
      e.target.value = '';
    }
  };

  const addFiles = (newFiles: File[]) => {
    const valid = newFiles.map((f) => ({
      file: f,
      id: `${f.name}-${Date.now()}-${Math.random()}`,
    }));
    setStagedFiles((prev) => [...prev, ...valid]);
  };

  const removeStagedFile = (id: string) => {
    setStagedFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const handleSequentialUpload = async () => {
    if (stagedFiles.length === 0) return;
    setUploadResults([]);
    const valid = stagedFiles.filter((f) => f.file.size <= 25 * 1024 * 1024);

    for (let i = 0; i < valid.length; i++) {
      const staged = valid[i];
      setUploadProgress({
        current: i + 1,
        total: valid.length,
        message: `Uploading ${staged.file.name}...`,
      });

      try {
        const res = await api.uploadDocument(staged.file);
        setUploadResults((prev) => [
          ...prev,
          { filename: staged.file.name, status: 'success', message: `Accepted (Job: ${res.job_id})` },
        ]);
      } catch (err: any) {
        setUploadResults((prev) => [
          ...prev,
          { filename: staged.file.name, status: 'error', message: err.message },
        ]);
      }
    }

    setUploadProgress(null);
    setStagedFiles([]);
    fetchDocs();
  };

  const handleDelete = async (id: string) => {
    if (confirm('Are you sure you want to delete this document permanently?')) {
      try {
        await api.deleteDocument(id);
        fetchDocs();
        setSelectedDocId(null);
        setSelectedDoc(null);
        setChunks([]);
      } catch (e: any) {
        alert(`Deletion failed: ${e.message}`);
      }
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Knowledge Base"
        subtitle="Upload, inspect, and manage enterprise documents, metadata, and embeddings."
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab('upload')}
              className="flex items-center gap-2 px-3 py-2 bg-[#2563EB] text-white rounded-lg text-sm font-medium hover:bg-[#1D4ED8] cursor-pointer"
            >
              <FileUp className="w-4 h-4" />
              Upload Documents
            </button>
            <button
              onClick={fetchDocs}
              className="p-2 border border-[#E2E8F0] bg-white rounded-lg hover:bg-[#F8FAFC]"
            >
              <RefreshCw className={`w-4 h-4 text-[#64748B] ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        }
      />

      {/* Tabs */}
      <div className="flex items-center border-b border-[#E2E8F0] gap-8">
        <button
          onClick={() => setActiveTab('inventory')}
          className={`pb-3 text-sm font-semibold border-b-2 flex items-center gap-2 transition-colors cursor-pointer ${
            activeTab === 'inventory'
              ? 'border-[#2563EB] text-[#2563EB]'
              : 'border-transparent text-[#64748B] hover:text-[#172B4D]'
          }`}
        >
          <FileText className="w-4 h-4" /> Document Inventory
        </button>
        <button
          onClick={() => setActiveTab('inspector')}
          className={`pb-3 text-sm font-semibold border-b-2 flex items-center gap-2 transition-colors cursor-pointer ${
            activeTab === 'inspector'
              ? 'border-[#2563EB] text-[#2563EB]'
              : 'border-transparent text-[#64748B] hover:text-[#172B4D]'
          }`}
        >
          <Search className="w-4 h-4" /> Document Inspector
        </button>
        <button
          onClick={() => setActiveTab('upload')}
          className={`pb-3 text-sm font-semibold border-b-2 flex items-center gap-2 transition-colors cursor-pointer ${
            activeTab === 'upload'
              ? 'border-[#2563EB] text-[#2563EB]'
              : 'border-transparent text-[#64748B] hover:text-[#172B4D]'
          }`}
        >
          <UploadCloud className="w-4 h-4" /> Drag & Drop Upload
        </button>
      </div>

      {/* TAB 1: Inventory */}
      {activeTab === 'inventory' && (
        <Card className="p-0 overflow-hidden">
          <div className="p-4 border-b border-[#E2E8F0] flex items-center justify-between">
            <div className="relative w-72">
              <Search className="w-4 h-4 text-[#94A3B8] absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search documents by filename..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg focus:outline-none focus:border-[#2563EB]"
              />
            </div>
            <span className="text-xs text-[#64748B]">
              Showing {docs.length} indexed document(s)
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-xs font-semibold text-[#64748B] uppercase">
                <tr>
                  <th className="px-6 py-3">Filename</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Pages</th>
                  <th className="px-4 py-3">Chunks</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Uploaded</th>
                  <th className="px-6 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {docs.map((d) => (
                  <tr key={d.id} className="hover:bg-[#F8FAFC]">
                    <td className="px-6 py-3 font-medium text-[#172B4D] flex items-center gap-2">
                      <FileText className="w-4 h-4 text-[#2563EB]" />
                      {d.filename}
                    </td>
                    <td className="px-4 py-3 uppercase text-xs font-semibold text-[#64748B]">
                      {d.file_type}
                    </td>
                    <td className="px-4 py-3">{d.page_count}</td>
                    <td className="px-4 py-3 font-semibold text-[#2563EB]">{d.chunk_count}</td>
                    <td className="px-4 py-3">
                      <Badge type={d.status === 'completed' ? 'success' : 'info'}>
                        {d.status.toUpperCase()}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-xs text-[#64748B]">{formatDate(d.created_at)}</td>
                    <td className="px-6 py-3 text-right">
                      <button
                        onClick={() => {
                          setSelectedDocId(d.id);
                          setActiveTab('inspector');
                        }}
                        className="text-xs font-semibold text-[#2563EB] hover:underline mr-4 cursor-pointer"
                      >
                        Inspect
                      </button>
                      <button
                        onClick={() => handleDelete(d.id)}
                        className="text-xs font-semibold text-[#DC2626] hover:underline cursor-pointer"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* TAB 2: Inspector */}
      {activeTab === 'inspector' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-1 space-y-4">
            <h2 className="text-sm font-bold text-[#172B4D] uppercase tracking-wider text-[#64748B]">
              Select Document
            </h2>
            <div className="space-y-1 max-h-[500px] overflow-y-auto">
              {docs.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelectedDocId(d.id)}
                  className={`w-full p-3 text-left rounded-lg text-xs font-medium transition-colors flex items-center justify-between cursor-pointer ${
                    selectedDocId === d.id
                      ? 'bg-[#2563EB] text-white'
                      : 'bg-[#F8FAFC] text-[#172B4D] hover:bg-[#E2E8F0]'
                  }`}
                >
                  <span className="truncate">{d.filename}</span>
                  <span className="text-[10px] opacity-75">{d.chunk_count} chunks</span>
                </button>
              ))}
            </div>
          </Card>

          <Card className="lg:col-span-2 space-y-6">
            {selectedDoc ? (
              <>
                <div className="flex items-center justify-between pb-4 border-b border-[#E2E8F0]">
                  <div>
                    <h2 className="text-lg font-bold text-[#172B4D]">{selectedDoc.filename}</h2>
                    <p className="text-xs text-[#64748B] font-mono">ID: {selectedDoc.id}</p>
                  </div>
                  <Badge type="success">{selectedDoc.status.toUpperCase()}</Badge>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
                  <div className="p-3 bg-[#F8FAFC] rounded-lg border border-[#E2E8F0]">
                    <div className="text-xs text-[#64748B]">Total Pages</div>
                    <div className="text-lg font-bold text-[#172B4D]">{selectedDoc.page_count}</div>
                  </div>
                  <div className="p-3 bg-[#F8FAFC] rounded-lg border border-[#E2E8F0]">
                    <div className="text-xs text-[#64748B]">Chunks</div>
                    <div className="text-lg font-bold text-[#2563EB]">{selectedDoc.chunk_count}</div>
                  </div>
                  <div className="p-3 bg-[#F8FAFC] rounded-lg border border-[#E2E8F0]">
                    <div className="text-xs text-[#64748B]">Format</div>
                    <div className="text-lg font-bold text-[#172B4D] uppercase">{selectedDoc.file_type}</div>
                  </div>
                  <div className="p-3 bg-[#F8FAFC] rounded-lg border border-[#E2E8F0]">
                    <div className="text-xs text-[#64748B]">Hash</div>
                    <div className="text-sm font-mono truncate text-[#172B4D]" title={selectedDoc.content_hash}>
                      {selectedDoc.content_hash.slice(0, 8)}...
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-bold text-[#172B4D] mb-3 flex items-center gap-2">
                    <Layers className="w-4 h-4 text-[#2563EB]" />
                    Indexed Document Chunks ({chunks.length})
                  </h3>
                  <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2">
                    {chunks.map((c) => (
                      <div
                        key={c.id}
                        className="p-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg text-xs space-y-1.5"
                      >
                        <div className="flex items-center justify-between font-semibold text-[#172B4D]">
                          <span>Chunk #{c.chunk_index} (Page {c.page_number})</span>
                          <span className="font-mono text-[10px] text-[#64748B]">Qdrant ID: {c.qdrant_point_id}</span>
                        </div>
                        <p className="text-[#475569] leading-relaxed whitespace-pre-wrap">{c.content_text}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="text-center py-16 text-sm text-[#64748B]">Select a document to inspect.</div>
            )}
          </Card>
        </div>
      )}

      {/* TAB 3: Drag & Drop Upload */}
      {activeTab === 'upload' && (
        <div className="space-y-6 max-w-3xl mx-auto">
          {/* Dropzone Area */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-2xl p-10 text-center transition-all bg-white cursor-pointer ${
              isDragging
                ? 'border-[#2563EB] bg-[#F0F7FF] scale-[1.01]'
                : 'border-[#CBD5E1] hover:border-[#2563EB] hover:bg-[#F8FAFC]'
            }`}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileSelect}
              multiple
              accept=".pdf,.txt,.csv,.docx,.json"
              className="hidden"
            />
            <div className="w-16 h-16 rounded-full bg-[#E0F2FE] text-[#2563EB] flex items-center justify-center mx-auto text-3xl mb-4">
              ☁️
            </div>
            <h2 className="text-xl font-bold text-[#172B4D]">Drag & Drop your files here</h2>
            <p className="text-sm text-[#64748B] mt-1">
              or click <span className="text-[#2563EB] font-semibold underline">Browse Files</span> to upload documents to your knowledge base
            </p>
            <div className="flex items-center justify-center gap-4 text-xs text-[#94A3B8] mt-6">
              <span>📄 Supported: <strong>PDF, TXT, CSV, DOCX, JSON</strong></span>
              <span>•</span>
              <span>⚖️ Max Size: <strong>25 MB per file</strong></span>
            </div>
          </div>

          {/* Staged Files Preview */}
          {stagedFiles.length > 0 && (
            <Card className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-[#172B4D]">
                  Staged for Ingestion ({stagedFiles.length} file{stagedFiles.length > 1 ? 's' : ''})
                </h3>
                <button
                  onClick={() => setStagedFiles([])}
                  className="text-xs text-[#DC2626] font-semibold hover:underline cursor-pointer"
                >
                  Clear All
                </button>
              </div>

              <div className="space-y-2">
                {stagedFiles.map((sf) => {
                  const isOversized = sf.file.size > 25 * 1024 * 1024;
                  return (
                    <div
                      key={sf.id}
                      className="p-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg flex items-center justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <FileText className="w-5 h-5 text-[#2563EB]" />
                        <div>
                          <div className="text-sm font-semibold text-[#172B4D]">{sf.file.name}</div>
                          <div className="text-xs text-[#64748B]">
                            {formatBytes(sf.file.size)}
                            {isOversized && (
                              <span className="text-[#DC2626] font-semibold ml-2">⚠️ Exceeds 25 MB</span>
                            )}
                          </div>
                        </div>
                      </div>
                      <button
                        onClick={() => removeStagedFile(sf.id)}
                        className="p-1 hover:bg-[#E2E8F0] rounded text-[#64748B] hover:text-[#DC2626] cursor-pointer"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  );
                })}
              </div>

              <button
                onClick={handleSequentialUpload}
                disabled={uploadProgress !== null || stagedFiles.some((f) => f.file.size > 25 * 1024 * 1024)}
                className="w-full py-3 bg-[#2563EB] hover:bg-[#1D4ED8] text-white rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50 transition-colors cursor-pointer"
              >
                <UploadCloud className="w-4 h-4" />
                Upload & Ingest {stagedFiles.length} Document{stagedFiles.length > 1 ? 's' : ''}
              </button>
            </Card>
          )}

          {/* Progress / Status */}
          {uploadProgress && (
            <Card className="p-4 bg-[#F0F7FF] border-[#BAE6FD] text-sm">
              <div className="flex items-center justify-between font-semibold text-[#0284C7] mb-2">
                <span>{uploadProgress.message}</span>
                <span>
                  {uploadProgress.current} / {uploadProgress.total}
                </span>
              </div>
              <div className="w-full bg-[#E0F2FE] h-2 rounded-full overflow-hidden">
                <div
                  className="bg-[#2563EB] h-full transition-all duration-300"
                  style={{ width: `${(uploadProgress.current / uploadProgress.total) * 100}%` }}
                />
              </div>
            </Card>
          )}

          {/* Results Summary */}
          {uploadResults.length > 0 && (
            <Card className="space-y-3">
              <h3 className="text-sm font-bold text-[#172B4D]">Ingestion Submission Results</h3>
              <div className="space-y-2">
                {uploadResults.map((r, i) => (
                  <div
                    key={i}
                    className={`p-3 rounded-lg text-xs flex items-center justify-between border ${
                      r.status === 'success'
                        ? 'bg-[#DCFCE7] border-[#BBF7D0] text-[#16A34A]'
                        : 'bg-[#FEE2E2] border-[#FECACA] text-[#DC2626]'
                    }`}
                  >
                    <span className="font-medium">{r.filename}</span>
                    <span>{r.message}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
