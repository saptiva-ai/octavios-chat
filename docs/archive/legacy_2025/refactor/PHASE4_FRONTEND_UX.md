# FASE 4: Frontend UI - Ciclo de Vida de Documentos

**Duración**: 1 día
**Owner**: Frontend team
**Dependencies**: Fase 3 completada (SSE events implemented)

---

## 🎯 Objetivos

1. Mostrar estado de documentos en tiempo real (uploading → processing → ready → failed)
2. Reaccionar a eventos SSE del backend
3. Nunca dejar la UI "colgada" sin feedback visual
4. Implementar chips de documentos con íconos de estado
5. Mostrar mensajes de sistema/warning/info en el chat

---

## 📋 Tareas (Mañana)

### 4.1 Tipos TypeScript para DocumentState

**File**: `apps/web/src/types/document.ts`

```typescript
/**
 * Document processing states (matches backend enum)
 */
export enum ProcessingStatus {
  UPLOADING = "uploading",
  PROCESSING = "processing",
  SEGMENTING = "segmenting",
  INDEXING = "indexing",
  READY = "ready",
  FAILED = "failed",
  ARCHIVED = "archived"
}

/**
 * Document state in conversation
 */
export interface DocumentState {
  doc_id: string;
  name: string;
  status: ProcessingStatus;
  error?: string;

  // Metadata
  pages?: number;
  size_bytes?: number;
  mimetype?: string;

  // Processing info
  segments_count: number;
  indexed_at?: string;  // ISO timestamp

  // Timestamps
  created_at: string;
  updated_at: string;
}

/**
 * SSE event types
 */
export type ChatSSEEvent =
  | { event: "chunk"; data: { content: string } }
  | { event: "done"; data: null }
  | { event: "error"; data: { error: string; message: string } }
  | {
      event: "system";
      data: {
        type: string;
        message: string;
        documents?: Array<{
          doc_id: string;
          name: string;
          status: ProcessingStatus;
          pages?: number;
        }>;
      };
    }
  | { event: "warning"; data: { message: string } }
  | { event: "info"; data: { message: string } }
  | {
      event: "document_ready";
      data: { doc_id: string; doc_name: string };
    };
```

---

### 4.2 Zustand Store para DocumentState

**File**: `apps/web/src/lib/stores/documentStore.ts`

```typescript
import { create } from "zustand";
import { DocumentState, ProcessingStatus } from "@/types/document";

interface DocumentStore {
  // State
  documents: Map<string, DocumentState>; // Keyed by doc_id

  // Actions
  addDocument: (doc: DocumentState) => void;
  updateDocumentStatus: (
    doc_id: string,
    status: ProcessingStatus,
    metadata?: Partial<DocumentState>
  ) => void;
  removeDocument: (doc_id: string) => void;
  getDocumentsBySession: (session_id: string) => DocumentState[];
  clearSession: (session_id: string) => void;
}

export const useDocumentStore = create<DocumentStore>((set, get) => ({
  documents: new Map(),

  addDocument: (doc) => {
    set((state) => {
      const newDocs = new Map(state.documents);
      newDocs.set(doc.doc_id, doc);
      return { documents: newDocs };
    });
  },

  updateDocumentStatus: (doc_id, status, metadata = {}) => {
    set((state) => {
      const newDocs = new Map(state.documents);
      const existing = newDocs.get(doc_id);

      if (existing) {
        newDocs.set(doc_id, {
          ...existing,
          status,
          ...metadata,
          updated_at: new Date().toISOString(),
        });
      }

      return { documents: newDocs };
    });
  },

  removeDocument: (doc_id) => {
    set((state) => {
      const newDocs = new Map(state.documents);
      newDocs.delete(doc_id);
      return { documents: newDocs };
    });
  },

  getDocumentsBySession: (session_id) => {
    // Filter documents by session
    // Note: We'll need to track session_id in DocumentState
    const allDocs = Array.from(get().documents.values());
    // For now, return all - can enhance later
    return allDocs;
  },

  clearSession: (session_id) => {
    // Remove all docs for a session
    set({ documents: new Map() });
  },
}));
```

---

### 4.3 DocumentChip Component

**File**: `apps/web/src/components/chat/DocumentChip.tsx`

```tsx
"use client";

import React from "react";
import { DocumentState, ProcessingStatus } from "@/types/document";
import {
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  Archive,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface DocumentChipProps {
  document: DocumentState;
  onRemove?: (doc_id: string) => void;
}

export function DocumentChip({ document, onRemove }: DocumentChipProps) {
  const { name, status, pages, error } = document;

  // Icon based on status
  const icon = (() => {
    switch (status) {
      case ProcessingStatus.UPLOADING:
      case ProcessingStatus.PROCESSING:
      case ProcessingStatus.SEGMENTING:
      case ProcessingStatus.INDEXING:
        return <Loader2 className="h-4 w-4 animate-spin" />;
      case ProcessingStatus.READY:
        return <CheckCircle2 className="h-4 w-4 text-green-600" />;
      case ProcessingStatus.FAILED:
        return <XCircle className="h-4 w-4 text-red-600" />;
      case ProcessingStatus.ARCHIVED:
        return <Archive className="h-4 w-4 text-gray-400" />;
      default:
        return <FileText className="h-4 w-4" />;
    }
  })();

  // Color based on status
  const colorClass = (() => {
    switch (status) {
      case ProcessingStatus.UPLOADING:
      case ProcessingStatus.PROCESSING:
      case ProcessingStatus.SEGMENTING:
      case ProcessingStatus.INDEXING:
        return "bg-blue-50 border-blue-200 text-blue-700";
      case ProcessingStatus.READY:
        return "bg-green-50 border-green-200 text-green-700";
      case ProcessingStatus.FAILED:
        return "bg-red-50 border-red-200 text-red-700";
      case ProcessingStatus.ARCHIVED:
        return "bg-gray-50 border-gray-200 text-gray-500";
      default:
        return "bg-gray-50 border-gray-200 text-gray-700";
    }
  })();

  // Status label
  const statusLabel = (() => {
    switch (status) {
      case ProcessingStatus.UPLOADING:
        return "Subiendo...";
      case ProcessingStatus.PROCESSING:
        return "Procesando...";
      case ProcessingStatus.SEGMENTING:
        return "Segmentando...";
      case ProcessingStatus.INDEXING:
        return "Indexando...";
      case ProcessingStatus.READY:
        return "Listo";
      case ProcessingStatus.FAILED:
        return "Error";
      case ProcessingStatus.ARCHIVED:
        return "Archivado";
    }
  })();

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 px-3 py-1.5 rounded-full border",
        "text-sm font-medium transition-colors",
        colorClass
      )}
      title={error || `${name} - ${statusLabel}`}
    >
      {icon}
      <span className="max-w-[200px] truncate">{name}</span>
      {pages && (
        <span className="text-xs opacity-70">({pages} págs)</span>
      )}
      {status === ProcessingStatus.FAILED && error && (
        <span className="text-xs opacity-70" title={error}>
          ⚠️
        </span>
      )}
      {onRemove && status !== ProcessingStatus.UPLOADING && (
        <button
          onClick={() => onRemove(document.doc_id)}
          className="ml-1 hover:opacity-70"
          aria-label="Remover documento"
        >
          ×
        </button>
      )}
    </div>
  );
}
```

---

### 4.4 SSE Event Handler con Document Updates

**File**: `apps/web/src/lib/chat/useSSEHandler.ts`

```typescript
import { useCallback } from "react";
import { useDocumentStore } from "@/lib/stores/documentStore";
import { ProcessingStatus } from "@/types/document";

export function useSSEHandler() {
  const { addDocument, updateDocumentStatus } = useDocumentStore();

  const handleSSEEvent = useCallback(
    (event: ChatSSEEvent) => {
      switch (event.event) {
        case "system":
          // Handle file ingestion system message
          if (event.data.type === "file_ingestion" && event.data.documents) {
            event.data.documents.forEach((doc) => {
              addDocument({
                doc_id: doc.doc_id,
                name: doc.name,
                status: doc.status,
                pages: doc.pages,
                segments_count: 0,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              });
            });
          }
          break;

        case "document_ready":
          // Update document status to READY
          updateDocumentStatus(
            event.data.doc_id,
            ProcessingStatus.READY,
            {
              indexed_at: new Date().toISOString(),
            }
          );
          break;

        case "warning":
        case "info":
          // Display as system message in chat
          // (handled by chat message store)
          break;

        case "chunk":
        case "done":
        case "error":
          // Handle in chat response logic
          break;
      }
    },
    [addDocument, updateDocumentStatus]
  );

  return { handleSSEEvent };
}
```

---

### 4.5 Chat Input con Document Chips

**File**: `apps/web/src/components/chat/ChatInput.tsx` (modificar)

```tsx
"use client";

import React, { useState } from "react";
import { DocumentChip } from "./DocumentChip";
import { useDocumentStore } from "@/lib/stores/documentStore";
import { ProcessingStatus } from "@/types/document";

export function ChatInput({ onSendMessage }: ChatInputProps) {
  const [message, setMessage] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);

  const { documents, addDocument } = useDocumentStore();

  const handleFileUpload = async (files: FileList) => {
    // Upload files and get doc_ids
    const uploaded = await uploadFiles(Array.from(files));

    // Add to store with UPLOADING status
    uploaded.forEach((doc) => {
      addDocument({
        doc_id: doc.id,
        name: doc.filename,
        status: ProcessingStatus.UPLOADING,
        size_bytes: doc.size,
        segments_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    });

    setAttachedFiles((prev) => [...prev, ...files]);
  };

  const handleRemoveFile = (doc_id: string) => {
    // Remove from UI (keep in store for history)
    setAttachedFiles((prev) =>
      prev.filter((f) => getFileDocId(f) !== doc_id)
    );
  };

  const currentSessionDocs = Array.from(documents.values());

  return (
    <div className="flex flex-col gap-2">
      {/* Document chips - show processing state */}
      {currentSessionDocs.length > 0 && (
        <div className="flex flex-wrap gap-2 p-2 bg-gray-50 rounded-lg">
          {currentSessionDocs.map((doc) => (
            <DocumentChip
              key={doc.doc_id}
              document={doc}
              onRemove={
                doc.status !== ProcessingStatus.UPLOADING
                  ? handleRemoveFile
                  : undefined
              }
            />
          ))}
        </div>
      )}

      {/* Message input */}
      <div className="flex items-center gap-2">
        <input
          type="file"
          multiple
          accept=".pdf,.png,.jpg"
          onChange={(e) => e.target.files && handleFileUpload(e.target.files)}
          className="hidden"
          id="file-upload"
        />
        <label
          htmlFor="file-upload"
          className="cursor-pointer p-2 hover:bg-gray-100 rounded"
        >
          📎
        </label>

        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Escribe tu mensaje..."
          className="flex-1 p-2 border rounded"
        />

        <button onClick={() => onSendMessage(message)}>Enviar</button>
      </div>
    </div>
  );
}
```

---

### 4.6 System Messages en Chat UI

**File**: `apps/web/src/components/chat/SystemMessage.tsx`

```tsx
"use client";

import React from "react";
import { Info, AlertTriangle, CheckCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type MessageType = "system" | "warning" | "info" | "success";

interface SystemMessageProps {
  type: MessageType;
  message: string;
  documents?: Array<{ name: string; status: string }>;
}

export function SystemMessage({
  type,
  message,
  documents,
}: SystemMessageProps) {
  const icon = (() => {
    switch (type) {
      case "warning":
        return <AlertTriangle className="h-5 w-5 text-yellow-600" />;
      case "info":
        return <Info className="h-5 w-5 text-blue-600" />;
      case "success":
        return <CheckCircle className="h-5 w-5 text-green-600" />;
      default:
        return <Info className="h-5 w-5 text-gray-600" />;
    }
  })();

  const bgClass = (() => {
    switch (type) {
      case "warning":
        return "bg-yellow-50 border-yellow-200";
      case "info":
        return "bg-blue-50 border-blue-200";
      case "success":
        return "bg-green-50 border-green-200";
      default:
        return "bg-gray-50 border-gray-200";
    }
  })();

  return (
    <div
      className={cn(
        "flex items-start gap-3 p-3 rounded-lg border my-2",
        bgClass
      )}
    >
      {icon}
      <div className="flex-1">
        <p className="text-sm">{message}</p>
        {documents && documents.length > 0 && (
          <ul className="mt-2 text-xs space-y-1">
            {documents.map((doc, idx) => (
              <li key={idx}>
                • {doc.name} - <em>{doc.status}</em>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
```

**Integrar en ChatMessages**:

```tsx
// apps/web/src/components/chat/ChatMessages.tsx

{messages.map((msg) => {
  if (msg.type === "system" || msg.type === "warning" || msg.type === "info") {
    return (
      <SystemMessage
        key={msg.id}
        type={msg.type}
        message={msg.content}
        documents={msg.metadata?.documents}
      />
    );
  }

  return <ChatBubble key={msg.id} message={msg} />;
})}
```

---

## 📋 Tareas (Tarde)

### 4.7 Polling para Document Status Updates

**File**: `apps/web/src/lib/chat/useDocumentStatusPolling.ts`

```typescript
import { useEffect } from "react";
import { useDocumentStore } from "@/lib/stores/documentStore";
import { ProcessingStatus } from "@/types/document";

/**
 * Poll backend for document status updates.
 *
 * Use when SSE doesn't send document_ready events (fallback).
 */
export function useDocumentStatusPolling(sessionId: string, enabled: boolean) {
  const { documents, updateDocumentStatus } = useDocumentStore();

  useEffect(() => {
    if (!enabled || !sessionId) return;

    const interval = setInterval(async () => {
      // Find processing documents
      const processingDocs = Array.from(documents.values()).filter(
        (doc) =>
          doc.status === ProcessingStatus.PROCESSING ||
          doc.status === ProcessingStatus.SEGMENTING ||
          doc.status === ProcessingStatus.INDEXING
      );

      if (processingDocs.length === 0) return;

      // Fetch status from backend
      try {
        const response = await fetch(
          `/api/chat/${sessionId}/documents/status`,
          {
            headers: { Authorization: `Bearer ${getToken()}` },
          }
        );

        const data = await response.json();

        // Update statuses
        data.documents.forEach((doc: any) => {
          const existing = documents.get(doc.doc_id);

          if (existing && existing.status !== doc.status) {
            updateDocumentStatus(doc.doc_id, doc.status, {
              segments_count: doc.segments_count,
              indexed_at: doc.indexed_at,
            });
          }
        });
      } catch (err) {
        console.error("Failed to poll document status:", err);
      }
    }, 3000); // Poll every 3 seconds

    return () => clearInterval(interval);
  }, [sessionId, enabled, documents, updateDocumentStatus]);
}
```

**Usage in ChatPage**:

```tsx
// apps/web/src/app/chat/[id]/page.tsx

export default function ChatPage({ params }: { params: { id: string } }) {
  const sessionId = params.id;

  // Poll for document updates (fallback if SSE fails)
  useDocumentStatusPolling(sessionId, true);

  // ... rest of component
}
```

---

## ✅ Acceptance Criteria

1. [ ] Document chips show correct status icons
2. [ ] Status updates in real-time (SSE or polling)
3. [ ] System/warning/info messages display in chat
4. [ ] No "colgado" state - always clear feedback
5. [ ] Failed documents show error icon + tooltip
6. [ ] Ready documents show green checkmark
7. [ ] Processing documents show spinning loader

---

## 📊 Visual Examples

**Document Chip States**:

```
📄 report.pdf (32 págs)  [🔄 Procesando...]   (blue, spinning)
📄 guide.pdf (10 págs)   [✅ Listo]           (green, checkmark)
📄 audit.pdf (45 págs)   [❌ Error]           (red, X icon)
```

**System Message**:

```
┌────────────────────────────────────────────┐
│ ℹ️  Recibí: report.pdf (32 págs),         │
│     guide.pdf (10 págs).                   │
│     Estoy procesando los documentos...     │
│                                             │
│     • report.pdf - processing              │
│     • guide.pdf - processing               │
└────────────────────────────────────────────┘
```

**Warning Message**:

```
┌────────────────────────────────────────────┐
│ ⚠️  No pude procesar corrupted.pdf.       │
│     Continuaré sin él.                     │
└────────────────────────────────────────────┘
```

---

## 🔗 Final Integration

Once Phase 4 is complete, the full system flow is:

1. **User uploads 3 PDFs** → UI shows chips with "Subiendo..."
2. **Backend receives files** → SSE event "system" → Chips update to "Procesando..."
3. **Worker processes docs** → When done, SSE "document_ready" → Chips show "✅ Listo"
4. **User asks question** → Backend retrieves segments → LLM responds with context
5. **Error occurs** → Warning message in chat, chips show error state, conversation continues

**Zero colgados, full visibility, graceful degradation.**
