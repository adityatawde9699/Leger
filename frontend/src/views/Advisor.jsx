import React from "react";
import { API_BASE, apiFetch, authHeaders } from "../lib";
import { useToast } from "../components/ui";
import { Sparkles, Send, Trash2, Plus, MessageSquare } from "lucide-react";

const SUGGESTIONS = [
  "Where am I overspending most?",
  "How can I save more this month?",
  "Am I on track with my budgets?",
  "Which subscriptions should I cut?",
  "Give me a monthly spending summary",
  "What's my biggest expense category?",
];

export default function Advisor() {
  const toast = useToast();
  const [conversations, setConversations] = React.useState([]);
  const [activeId, setActiveId]           = React.useState(null);
  const [messages, setMessages]           = React.useState([]);
  const [input, setInput]                 = React.useState("");
  const [streaming, setStreaming]         = React.useState(false);
  const [loadingConvs, setLoadingConvs]   = React.useState(true);
  const [showConvs, setShowConvs]         = React.useState(false);
  const chatRef  = React.useRef(null);
  const inputRef = React.useRef(null);

  async function loadConversations() {
    try {
      const convs = await apiFetch("/conversations");
      setConversations(convs);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setLoadingConvs(false);
    }
  }

  async function openConversation(id) {
    setActiveId(id);
    setShowConvs(false);
    try {
      const msgs = await apiFetch(`/conversations/${id}/messages`);
      setMessages(msgs.map((m) => ({ role: m.role, text: m.content })));
    } catch (e) {
      toast(e.message, "error");
    }
  }

  React.useEffect(() => { loadConversations(); }, []);

  React.useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages]);

  async function send() {
    const q = input.trim();
    if (!q || streaming) return;

    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setStreaming(true);
    setMessages((m) => [...m, { role: "assistant", text: "" }]);

    try {
      const body = JSON.stringify({ question: q, conversation_id: activeId || undefined });
      const res  = await fetch(`${API_BASE}/advisor/stream`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const newConvId = res.headers.get("X-Conversation-Id");
      if (newConvId && !activeId) {
        setActiveId(newConvId);
        loadConversations();
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6);
          if (data === "[DONE]") break;
          if (data.startsWith("[ERROR]")) { toast(data.slice(7).trim(), "error"); break; }
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: "assistant",
              text: (updated[updated.length - 1].text || "") + data,
            };
            return updated;
          });
        }
      }
    } catch (e) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", text: "Error reaching AI. Please try again." };
        return updated;
      });
      toast(e.message, "error");
    } finally {
      setStreaming(false);
      inputRef.current?.focus();
    }
  }

  function newConversation() {
    setActiveId(null);
    setMessages([]);
    setShowConvs(false);
  }

  async function deleteConversation(id, e) {
    e.stopPropagation();
    if (!window.confirm("Delete this conversation?")) return;
    try {
      await apiFetch(`/conversations/${id}`, { method: "DELETE" });
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeId === id) newConversation();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  const TypingDots = () => (
    <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center', padding: '2px 0' }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: 6, height: 6, borderRadius: '50%', background: 'var(--text-muted)',
          animation: 'pulse 1.2s ease-in-out infinite',
          animationDelay: `${i * 0.2}s`,
        }} />
      ))}
    </span>
  );

  return (
    <div className="view-advisor">
      <div className="advisor-layout">
        {/* Backdrop for the mobile conversation sheet */}
        {showConvs && <div className="advisor-backdrop" onClick={() => setShowConvs(false)} aria-hidden="true" />}

        {/* Sidebar */}
        <aside className={`advisor-sidebar${showConvs ? " open" : ""}`}>
          <div className="advisor-sidebar-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <MessageSquare size={16} style={{ color: 'var(--primary)' }} />
              <span>Conversations</span>
            </div>
            <button
              className="btn-primary"
              style={{ fontSize: 12, padding: '6px 12px' }}
              onClick={newConversation}
            >
              <Plus size={12} /> New
            </button>
          </div>

          <div style={{ overflowY: 'auto', maxHeight: '60vh' }}>
            {loadingConvs ? (
              <div style={{ padding: 16 }}>
                <div className="skeleton" style={{ height: 56, borderRadius: 10 }} />
              </div>
            ) : conversations.length === 0 ? (
              <div style={{ padding: '32px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13, fontWeight: 500 }}>
                No conversations yet.<br />Ask your first question!
              </div>
            ) : (
              conversations.map((c) => (
                <div key={c.id} style={{ display: 'flex', alignItems: 'center', borderBottom: '1px solid var(--border)' }}>
                  <button
                    className={`advisor-conv-item${activeId === c.id ? " active" : ""}`}
                    onClick={() => openConversation(c.id)}
                    style={{ flex: 1, minWidth: 0 }}
                  >
                    <div className="advisor-conv-title">{c.title || "Conversation"}</div>
                    <div className="advisor-conv-date">
                      {new Date(c.updated_at).toLocaleDateString("en-IN")}
                    </div>
                  </button>
                  <button
                    onClick={(e) => deleteConversation(c.id, e)}
                    title="Delete"
                    style={{ padding: '8px 12px', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', flexShrink: 0, transition: 'color 0.2s' }}
                    onMouseEnter={e => e.currentTarget.style.color = 'var(--negative)'}
                    onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* Main chat */}
        <div className="advisor-main">
          <div style={{ marginBottom: 24 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
              <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
                <div style={{ width: 40, height: 40, borderRadius: 12, background: 'linear-gradient(135deg, var(--primary), var(--info))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Sparkles size={20} style={{ color: 'white' }} />
                </div>
                Amadeus AI
              </h1>
              <button
                className="mobile-only-inline btn-link"
                onClick={() => setShowConvs(!showConvs)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 12px', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 12 }}
              >
                <MessageSquare size={15} />
                <span>History</span>
              </button>
            </div>
            <p className="page-subtitle" style={{ marginBottom: 0 }}>Your personal financial advisor, powered by AI</p>
          </div>

          {/* Suggestion chips */}
          {messages.length === 0 && (
            <div className="advisor-suggestions">
              {SUGGESTIONS.map((q) => (
                <button key={q} className="suggestion-chip"
                  onClick={() => { setInput(q); inputRef.current?.focus(); }}>
                  {q}
                </button>
              ))}
            </div>
          )}

          {/* Chat window */}
          <div className="chat-window" ref={chatRef}>
            {messages.length === 0 && (
              <div className="chat-empty" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, margin: 'auto', textAlign: 'center' }}>
                <div style={{ width: 56, height: 56, borderRadius: 16, background: 'linear-gradient(135deg, rgba(56,189,248,0.12), rgba(56,189,248,0.16))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Sparkles size={24} style={{ color: 'var(--primary)' }} />
                </div>
                <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>How can I help you today?</div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)', maxWidth: 300, lineHeight: 1.6 }}>
                  Your financial data is loaded. Ask me anything about your spending, savings, or budgets.
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble ${m.role}`}>
                {m.role === "assistant" && (
                  <div className="chat-label">
                    <Sparkles size={11} /> Amadeus AI
                  </div>
                )}
                <div className="chat-text">
                  {m.text || (streaming && i === messages.length - 1 ? <TypingDots /> : "")}
                </div>
              </div>
            ))}
          </div>

          {/* Input */}
          <div className="chat-input-row">
            <input
              ref={inputRef}
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
              placeholder="Ask about your spending, savings, budgets…"
              disabled={streaming}
            />
            <button
              className="btn-primary chat-send"
              onClick={send}
              disabled={streaming || !input.trim()}
              style={{ borderRadius: 99, padding: '0 24px', minWidth: 56, height: 52 }}
            >
              {streaming
                ? <span style={{ display: 'inline-flex', gap: 3 }}>{[0,1,2].map(i => <span key={i} style={{ width: 5, height: 5, borderRadius: '50%', background: 'white', opacity: 0.8, animation: 'pulse 1.2s ease-in-out infinite', animationDelay: `${i*0.2}s` }} />)}</span>
                : <Send size={16} />
              }
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
