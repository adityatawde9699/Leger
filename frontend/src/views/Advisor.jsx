import React from "react";
import { API_BASE, apiFetch, money, CATEGORY_COLORS } from "../lib";
import { useToast } from "../components/ui";
import { Sparkles, Send } from "lucide-react";

const SUGGESTIONS = [
  "Where am I overspending most?",
  "How can I save more this month?",
  "Am I on track with my budgets?",
  "Which subscriptions should I cut?",
];

const SYSTEM_NOTE = "Your financial data is loaded. Ask me anything about your spending, savings, or budgets.";

export default function Advisor() {
  const toast = useToast();
  const [conversations, setConversations] = React.useState([]);
  const [activeId, setActiveId] = React.useState(null);
  const [messages, setMessages] = React.useState([]);
  const [input, setInput] = React.useState("");
  const [streaming, setStreaming] = React.useState(false);
  const [loadingConvs, setLoadingConvs] = React.useState(true);
  const chatRef = React.useRef(null);

  // Load conversation list
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

  // Load messages for a conversation
  async function openConversation(id) {
    setActiveId(id);
    try {
      const msgs = await apiFetch(`/conversations/${id}/messages`);
      setMessages(msgs.map((m) => ({ role: m.role, text: m.content })));
    } catch (e) {
      toast(e.message, "error");
    }
  }

  React.useEffect(() => { loadConversations(); }, []);

  // Auto-scroll chat
  React.useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  async function send() {
    const q = input.trim();
    if (!q || streaming) return;

    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setStreaming(true);

    // Placeholder for streaming response
    setMessages((m) => [...m, { role: "assistant", text: "" }]);

    try {
      const token = localStorage.getItem("ledger_token") || "dev-user";
      const body = JSON.stringify({ question: q, conversation_id: activeId || undefined });

      const res = await fetch(`${API_BASE}/advisor/stream`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // Read new conversation ID from header
      const newConvId = res.headers.get("X-Conversation-Id");
      if (newConvId && !activeId) {
        setActiveId(newConvId);
        loadConversations();
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // keep incomplete line

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6);
          if (data === "[DONE]") break;
          if (data.startsWith("[ERROR]")) {
            toast(data.slice(7).trim(), "error");
            break;
          }
          // Append token to last assistant message
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
    }
  }

  function newConversation() {
    setActiveId(null);
    setMessages([]);
  }

  return (
    <div className="view-advisor">
      <div className="advisor-layout">
        {/* ── Sidebar: conversation history ── */}
        <aside className="advisor-sidebar">
          <div className="advisor-sidebar-header">
            <span>Conversations</span>
            <button className="btn-secondary" style={{ fontSize: 12, padding: "4px 10px" }}
              onClick={newConversation}>
              + New
            </button>
          </div>
          {loadingConvs ? (
            <div className="skeleton" style={{ height: 40, margin: 8, borderRadius: 8 }} />
          ) : conversations.length === 0 ? (
            <div className="advisor-no-convs">No conversations yet</div>
          ) : (
            conversations.map((c) => (
              <button key={c.id}
                className={`advisor-conv-item${activeId === c.id ? " active" : ""}`}
                onClick={() => openConversation(c.id)}>
                <div className="advisor-conv-title">{c.title || "Conversation"}</div>
                <div className="advisor-conv-date">
                  {new Date(c.updated_at).toLocaleDateString("en-IN")}
                </div>
              </button>
            ))
          )}
        </aside>

        {/* ── Main chat area ── */}
        <div className="advisor-main">
          <div className="page-title-block">
            <h1 className="page-title">
              <Sparkles size={22} style={{ verticalAlign: "middle", marginRight: 8, color: "var(--accent)" }} />
              AI Advisor
            </h1>
            <p className="page-subtitle">
              Powered by {typeof window !== "undefined" && localStorage.getItem("llama_enabled") ? "local AI (private)" : "Claude AI"}
            </p>
          </div>

          {/* Suggestions shown when no messages */}
          {messages.length === 0 && (
            <div className="advisor-suggestions">
              {SUGGESTIONS.map((q) => (
                <button key={q} className="suggestion-chip"
                  onClick={() => { setInput(q); }}>
                  {q}
                </button>
              ))}
            </div>
          )}

          {/* Chat window */}
          <div className="chat-window" ref={chatRef}>
            {messages.length === 0 && (
              <div className="chat-empty">{SYSTEM_NOTE}</div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble ${m.role}`}>
                {m.role === "assistant" && (
                  <div className="chat-label">
                    <Sparkles size={11} /> Ledger AI
                  </div>
                )}
                <div className="chat-text">
                  {m.text || (streaming && i === messages.length - 1 && (
                    <span className="typing-dots">
                      <span /><span /><span />
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Input */}
          <div className="chat-input-row">
            <input
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
              placeholder="Ask about your spending, savings, budgets…"
              disabled={streaming}
            />
            <button className="btn-primary chat-send" onClick={send} disabled={streaming || !input.trim()}>
              {streaming ? "…" : <Send size={15} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
